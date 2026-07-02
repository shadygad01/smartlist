import { pgTable, text, serial, integer, numeric, timestamp, pgEnum } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const transactionTypeEnum = pgEnum("transaction_type", ["BUY", "SELL"]);
export const uploadStatusEnum = pgEnum("upload_status", ["pending", "parsed", "failed", "duplicate"]);

export const portfolioUploadsTable = pgTable("portfolio_uploads", {
  id: serial("id").primaryKey(),
  fileName: text("file_name").notNull(),
  fileHash: text("file_hash").notNull().unique(),
  objectPath: text("object_path").notNull(),
  contentType: text("content_type").notNull(),
  status: uploadStatusEnum("status").notNull().default("pending"),
  transactionCount: integer("transaction_count").default(0),
  errorMessage: text("error_message"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  parsedAt: timestamp("parsed_at"),
});

export const portfolioTransactionsTable = pgTable("portfolio_transactions", {
  id: serial("id").primaryKey(),
  uploadId: integer("upload_id").references(() => portfolioUploadsTable.id),
  ticker: text("ticker").notNull(),
  transactionType: transactionTypeEnum("transaction_type").notNull().default("BUY"),
  quantity: numeric("quantity", { precision: 18, scale: 4 }).notNull(),
  price: numeric("price", { precision: 18, scale: 4 }).notNull(),
  tradeDate: timestamp("trade_date").notNull(),
  notes: text("notes"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

export const insertPortfolioUploadSchema = createInsertSchema(portfolioUploadsTable).omit({ id: true, createdAt: true });
export const insertPortfolioTransactionSchema = createInsertSchema(portfolioTransactionsTable).omit({ id: true, createdAt: true });

export type PortfolioUpload = typeof portfolioUploadsTable.$inferSelect;
export type InsertPortfolioUpload = z.infer<typeof insertPortfolioUploadSchema>;
export type PortfolioTransaction = typeof portfolioTransactionsTable.$inferSelect;
export type InsertPortfolioTransaction = z.infer<typeof insertPortfolioTransactionSchema>;
