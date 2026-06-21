import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================

# Path to your pre-downloaded historical data CSV (wide format)
DATA_FILE_PATH = 'egypt_stocks_5yr_data_updated.csv'

# List of all 27 stocks (ensure these match symbols in your CSV)
from config.scanner_config import get_constitutional_universe
STOCKS = get_constitutional_universe()

# Whitelist for specific Price Gate thresholds
WHITELIST = ["FWRY.CA", "EAST.CA", "ETEL.CA", "EMFD.CA", "PHDC.CA", "HRHO.CA", "MCQE.CA", "OIH.CA", "GBCO.CA"]

# Strategy Thresholds
SCORE_MIN = 35
PRICE_GATE_WHITELIST = 12
PRICE_GATE_NORMAL = 18
MAX_AVERAGES = 3
EXIT_TARGET_FACTOR = 0.95 # Exit at 95% of the 80-day high
MAX_HOLD_DAYS = 365 # Exit after 1 year if target not met

# Weights for Price Score calculation
W_PRICE = 30

# ==============================================================================
# DATA PREPROCESSING FUNCTIONS
# ==============================================================================

def convert_wide_to_long_format(input_path, symbols):
    print(f"Starting conversion of {input_path} to long format...")
    
    # Read the CSV with no header initially to inspect structure
    df_raw = pd.read_csv(input_path, header=None, low_memory=False)
    
    # The first row contains general column names (Date, Close, High, etc.)
    # The second row contains the symbol for each set of columns
    
    # Extract the first two header rows
    general_headers = df_raw.iloc[0].tolist()
    symbol_headers = df_raw.iloc[1].tolist()
    
    long_data = []

    # Iterate through the data rows (starting from index 2)
    for row_idx in range(2, len(df_raw)):
        current_row_data = df_raw.iloc[row_idx]
        
        # Extract the Date from the first column
        date_str = current_row_data[0]
        try:
            current_date = pd.to_datetime(date_str)
        except ValueError:
            # print(f"Skipping row {row_idx} due to invalid date format: {date_str}")
            continue

        # Iterate through symbols to extract their data for the current date
        for symbol in symbols:
            # Find the starting column index for this symbol's data block
            try:
                # Find the index where the symbol first appears in the symbol_headers row
                symbol_start_col_idx = symbol_headers.index(symbol)
            except ValueError:
                # If symbol not found in symbol_headers, it might not have data in this file
                continue
            
            # Ensure we don't go out of bounds
            if symbol_start_col_idx + 5 > len(general_headers):
                continue

            # Verify the general headers match the expected metrics for this block
            expected_metrics = ['Close', 'High', 'Low', 'Open', 'Volume']
            actual_metrics_in_block = [general_headers[symbol_start_col_idx + i] for i in range(5)]

            if actual_metrics_in_block == expected_metrics:
                stock_data = {
                    'Date': current_date,
                    'Symbol': symbol,
                    'Close': current_row_data[symbol_start_col_idx],
                    'High': current_row_data[symbol_start_col_idx + 1],
                    'Low': current_row_data[symbol_start_col_idx + 2],
                    'Open': current_row_data[symbol_start_col_idx + 3],
                    'Volume': current_row_data[symbol_start_col_idx + 4]
                }
                long_data.append(stock_data)

    if not long_data:
        print("Error: No data was processed for any symbol. Check your symbols list and CSV header format.")
        return None

    long_df = pd.DataFrame(long_data)
    long_df['Date'] = pd.to_datetime(long_df['Date'])
    long_df = long_df.set_index('Date')
    long_df = long_df.sort_values(by=['Date', 'Symbol'])
    
    # In this specific CSV, 'Close' is already adjusted, so we can use it directly as 'Adj Close'
    long_df['Adj Close'] = long_df['Close']
    
    # Convert numeric columns to appropriate types
    for col in ['Close', 'High', 'Low', 'Open', 'Volume', 'Adj Close']:
        if col in long_df.columns:
            long_df[col] = pd.to_numeric(long_df[col], errors='coerce')
            
    long_df.dropna(subset=['Adj Close'], inplace=True) # Drop rows where Adj Close is NaN
    print(f"Conversion complete. Total rows in long format: {len(long_df)}")
    return long_df

# ==============================================================================
# CORE LOGIC FUNCTIONS (Copied directly from previous backtest logic)
# ==============================================================================

def calculate_swings(df_window, length=80):
    if len(df_window) < length: return None
    
    hi = float(df_window['High'].max())
    lo = float(df_window['Low'].min())
    
    rng = hi - lo
    if rng <= 0: return None
    
    eq = lo + rng * 0.5
    buy_hi = lo + rng * 0.15
    z3_level = lo + rng * 0.05
    
    return hi, lo, eq, buy_hi, z3_level

def score_price_position(cur_price, lo, hi, eq, buy_hi):
    if cur_price >= eq: return 0
    if cur_price <= buy_hi:
        ratio = (cur_price - lo) / (buy_hi - lo) if (buy_hi - lo) > 0 else 0
        return max(round(W_PRICE * (1.0 - ratio * 0.40)), 0)
    ratio = (cur_price - buy_hi) / (eq - buy_hi) if (eq - buy_hi) > 0 else 1
    return max(round(W_PRICE * 0.60 * (1.0 - ratio)), 0)

# ==============================================================================
# BACKTEST ENGINE
# ==============================================================================

def run_backtest(all_data_long_format):
    print(f"\n🚀 Starting Backtest with {len(all_data_long_format)} data points.")
    print("-" * 60)

    trades_results = []
    active_trades = [] # Stores currently open trades

    # Get all unique dates from the data
    all_dates = all_data_long_format.index.unique().sort_values()

    for current_date in all_dates:
        # Process active trades first (check for exits/averaging)
        trades_to_remove = []
        for trade in active_trades:
            symbol = trade['Symbol']
            
            # Get data for the current symbol up to current_date
            symbol_data = all_data_long_format[(all_data_long_format['Symbol'] == symbol) & (all_data_long_format.index <= current_date)]
            if symbol_data.empty: continue
            
            cur_price = float(symbol_data['Adj Close'].iloc[-1])
            
            # Check for Exit (Target or Timeout)
            entry_price = trade['Entries'][0]['price'] # Price of initial entry
            current_hold_days = (current_date - trade['Entry_Date']).days

            # Exit conditions
            exit_reason = None
            if cur_price >= trade['Target']:
                exit_reason = 'Target Hit'
            elif current_hold_days >= MAX_HOLD_DAYS:
                exit_reason = 'Max Hold Days'
            
            if exit_reason:
                # Calculate final P&L for the trade
                final_entry_price = sum(e['price'] for e in trade['Entries']) / len(trade['Entries'])
                final_pnl = (cur_price - final_entry_price) / final_entry_price
                
                trades_results.append({
                    'Symbol': symbol,
                    'Entry_Date': trade['Entry_Date'].strftime('%Y-%m-%d'),
                    'Exit_Date': current_date.strftime('%Y-%m-%d'),
                    'Entry_Price': round(final_entry_price, 2),
                    'Exit_Price': round(cur_price, 2),
                    'PNL_Percentage': round(final_pnl * 100, 2),
                    'Hold_Days': current_hold_days,
                    'Exit_Reason': exit_reason,
                    'Num_Averages': trade['Averages_Done']
                })
                trades_to_remove.append(trade)
                continue # Move to next trade after exiting

            # Check for Averaging Down (Z3)
            if trade['Averages_Done'] < MAX_AVERAGES:
                if cur_price <= trade['Z3_Level']:
                    # Prevent averaging if already averaged on the same day or very recently
                    last_avg_date = trade['Entries'][-1]['date']
                    if (current_date - last_avg_date).days > 0: # Ensure at least 1 day passed
                        # Ensure price is significantly lower than last entry to avoid micro-averaging
                        last_entry_price = trade['Entries'][-1]['price']
                        if cur_price < last_entry_price * 0.98: # At least 2% lower
                            trade['Entries'].append({'date': current_date, 'price': cur_price, 'type': 'Average'})
                            trade['Averages_Done'] += 1
                            # For this backtest, we'll keep the original Z3 and Target from initial entry for consistency

        # Remove exited trades
        for trade in trades_to_remove:
            active_trades.remove(trade)

        # Scan for new signals for all stocks on current_date
        for symbol in STOCKS:
            # Skip if already have an active trade for this symbol (prevents overlapping trades for the same symbol)
            # This is a key difference from previous backtest, making it more conservative
            if any(t['Symbol'] == symbol for t in active_trades): 
                continue

            symbol_data = all_data_long_format[(all_data_long_format['Symbol'] == symbol) & (all_data_long_format.index <= current_date)]
            if len(symbol_data) < 80: continue
            
            df_window = symbol_data.iloc[-80:] # Use last 80 days for swings
            if df_window.empty: continue

            cur_price = float(symbol_data['Adj Close'].iloc[-1])
            
            swings_data = calculate_swings(df_window)
            if not swings_data: continue
            hi, lo, eq, buy_hi, z3_level = swings_data

            # 1. Price Gate Check
            p_score = score_price_position(cur_price, lo, hi, eq, buy_hi)
            gate_threshold = PRICE_GATE_WHITELIST if symbol in WHITELIST else PRICE_GATE_NORMAL
            
            # 2. Total Score Calculation (Price Score + 15 points baseline)
            total_score = p_score + 15 
            
            # Check for BUY/ENTRY signal
            if p_score >= gate_threshold and total_score >= SCORE_MIN:
                # Prevent adding duplicate signals on the same day for the same symbol
                if not any(t['Symbol'] == symbol and t['Entry_Date'] == current_date for t in active_trades):
                    active_trades.append({
                        'Symbol': symbol,
                        'Entry_Date': current_date,
                        'Entries': [{'date': current_date, 'price': cur_price, 'type': 'Initial'}],
                        'Z3_Level': z3_level,
                        'Target': hi * EXIT_TARGET_FACTOR, 
                        'Status': 'Active',
                        'Averages_Done': 0
                    })

    # Close any remaining active trades at the last available price
    last_date = all_dates[-1]
    for trade in active_trades:
        symbol = trade['Symbol']
        symbol_data = all_data_long_format[(all_data_long_format['Symbol'] == symbol) & (all_data_long_format.index <= last_date)]
        if symbol_data.empty: continue
        
        cur_price = float(symbol_data['Adj Close'].iloc[-1])
        final_entry_price = sum(e['price'] for e in trade['Entries']) / len(trade['Entries'])
        final_pnl = (cur_price - final_entry_price) / final_entry_price
        current_hold_days = (last_date - trade['Entry_Date']).days

        trades_results.append({
            'Symbol': symbol,
            'Entry_Date': trade['Entry_Date'].strftime('%Y-%m-%d'),
            'Exit_Date': last_date.strftime('%Y-%m-%d'),
            'Entry_Price': round(final_entry_price, 2),
            'Exit_Price': round(cur_price, 2),
            'PNL_Percentage': round(final_pnl * 100, 2),
            'Hold_Days': current_hold_days,
            'Exit_Reason': 'Forced Close (End of Backtest)',
            'Num_Averages': trade['Averages_Done']
        })

    results_df = pd.DataFrame(trades_results)
    return results_df

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    # 1. Convert wide format data to long format
    processed_data = convert_wide_to_long_format(DATA_FILE_PATH, STOCKS)
    
    if processed_data is None:
        print("Exiting backtest due to data processing error.")
    else:
        # 2. Run the backtest with the processed data
        backtest_results = run_backtest(processed_data)
        
        if backtest_results is not None and not backtest_results.empty:
            # Save detailed results
            output_filename = 'standalone_backtest_results.csv'
            backtest_results.to_csv(output_filename, index=False)
            print(f"\n✅ Detailed backtest results saved to {output_filename}")
            
            # Calculate and print summary statistics
            total_trades = len(backtest_results)
            winning_trades = backtest_results[backtest_results['PNL_Percentage'] > 0]
            total_winning_trades = len(winning_trades)
            
            avg_pnl_per_trade = backtest_results['PNL_Percentage'].mean()
            win_rate = (total_winning_trades / total_trades) * 100 if total_trades > 0 else 0
            
            print("\n--- Backtest Summary ---")
            print(f"Total Trades: {total_trades}")
            print(f"Winning Trades: {total_winning_trades}")
            print(f"Average PNL per Trade: {avg_pnl_per_trade:.2f}%")
            print(f"Win Rate: {win_rate:.2f}%")
            
            # Placeholder for CAGR and Drawdown (requires more complex portfolio simulation)
            print("\nNote: CAGR and Max Drawdown require a full portfolio simulation with capital management.")
            print("This script focuses on per-trade statistics for replication purposes.")
        else:
            print("No trades generated or an error occurred during backtest.")
