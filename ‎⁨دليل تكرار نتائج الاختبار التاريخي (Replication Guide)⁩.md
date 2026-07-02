# دليل تكرار نتائج الاختبار التاريخي (Replication Guide)

## مقدمة

يهدف هذا الدليل إلى توفير التعليمات اللازمة لتشغيل سكربت الاختبار التاريخي المستقل (`standalone_backtest_script.py`) باستخدام ملف البيانات التاريخية الذي تم توفيره (`egypt_stocks_5yr_data_updated.csv`). باتباع هذه التعليمات، يمكنك التأكد من أن أي بيئة برمجية أو نموذج ذكاء اصطناعي آخر (مثل Claude أو ChatGPT) يمكنه محاكاة نفس منطق التداول والوصول إلى نفس النتائج التي تم تحقيقها.

## 1. المتطلبات الأساسية

*   **بيئة Python:** يجب أن تكون لديك بيئة Python 3.x مثبتة.
*   **المكتبات:** ستحتاج إلى تثبيت مكتبات `pandas` و `numpy`.
    ```bash
    pip install pandas numpy
    ```
*   **ملف البيانات التاريخية:** ملف `egypt_stocks_5yr_data_updated.csv` الذي يحتوي على بيانات الأسهم المصرية لمدة 5 سنوات.
*   **سكربت الاختبار التاريخي:** ملف `standalone_backtest_script.py`.

## 2. إعداد الملفات

تأكد من أن ملفي `egypt_stocks_5yr_data_updated.csv` و `standalone_backtest_script.py` موجودان في نفس المجلد.

## 3. فهم سكربت الاختبار (`standalone_backtest_script.py`)

السكربت مصمم ليكون مستقلاً ويحتوي على الأقسام الرئيسية التالية:

### أ. التكوين والثوابت (CONFIGURATION & CONSTANTS)

يحتوي هذا القسم على المتغيرات التي يمكنك تعديلها:

*   `DATA_FILE_PATH`: مسار ملف البيانات التاريخية (لا تقم بتغييره إذا كان الملف في نفس المجلد).
*   `STOCKS`: قائمة برموز الأسهم الـ 27 التي سيتم اختبارها.
*   `WHITELIST`: قائمة بالأسهم التي لها عتبة Price Gate أقل.
*   `SCORE_MIN`: الحد الأدنى للسكور الإجمالي لبدء الشراء (محدد بـ 35).
*   `PRICE_GATE_WHITELIST`: عتبة Price Gate لأسهم القائمة البيضاء (محددة بـ 12).
*   `PRICE_GATE_NORMAL`: عتبة Price Gate للأسهم العادية (محددة بـ 18).
*   `MAX_AVERAGES`: الحد الأقصى لمرات التعزيز (محدد بـ 3).
*   `EXIT_TARGET_FACTOR`: عامل تحديد الهدف (محدد بـ 0.95، أي 95% من أعلى سعر في 80 يوماً).
*   `MAX_HOLD_DAYS`: أقصى مدة للاحتفاظ بالصفقة قبل الإغلاق القسري (محددة بـ 365 يوماً).
*   `W_PRICE`: وزن سكور السعر في حساب السكور الإجمالي (محدد بـ 30).

### ب. وظائف معالجة البيانات (DATA PREPROCESSING FUNCTIONS)

*   `convert_wide_to_long_format(input_path, symbols)`: هذه الوظيفة هي الأهم لضمان قراءة البيانات بشكل صحيح. تقوم بتحويل ملف CSV ذي التنسيق العريض (حيث كل سهم له عدة أعمدة) إلى تنسيق طولي (حيث كل صف يمثل بيانات يوم واحد لسهم واحد). تم تصميمها خصيصاً للتعامل مع هيكل الرأس المعقد لملف `egypt_stocks_5yr_data_updated.csv`.

### ج. وظائف المنطق الأساسي (CORE LOGIC FUNCTIONS)

*   `calculate_swings(df_window, length=80)`: تحسب مستويات الدعم والمقاومة (High, Low, Eq, Buy_Hi, Z3_Level) بناءً على آخر 80 يوماً.
*   `score_price_position(cur_price, lo, hi, eq, buy_hi)`: تحسب سكور موقع السعر بناءً على موقعه الحالي بالنسبة لمستويات الدعم والمقاومة.

### د. محرك الاختبار التاريخي (BACKTEST ENGINE)

*   `run_backtest(all_data_long_format)`: هذه هي الوظيفة الرئيسية التي تحاكي التداول يوماً بيوم. تتضمن:
    *   **منع الصفقات المتداخلة:** لا يتم فتح صفقة جديدة لنفس السهم إلا بعد إغلاق الصفقة السابقة (هذا هو الاختلاف الرئيسي عن الاختبارات الأولية التي سمحت بتداخل الصفقات).
    *   **منطق الدخول:** يتم الشراء عندما يكون `p_score >= gate_threshold` و `total_score >= SCORE_MIN`.
    *   **منطق التعزيز:** يتم التعزيز عند `cur_price <= trade['Z3_Level']` بحد أقصى `MAX_AVERAGES` مرات، مع شرط أن يكون السعر أقل بنسبة 2% على الأقل من آخر سعر دخول لمنع التعزيزات الصغيرة جداً.
    *   **منطق الخروج:** عند تحقيق الهدف (`Target`) أو تجاوز أقصى مدة احتفاظ (`MAX_HOLD_DAYS`).

## 4. كيفية التشغيل

للتشغيل، افتح Terminal أو Command Prompt، انتقل إلى المجلد الذي يحتوي على الملفات، ثم نفذ الأمر التالي:

```bash
python standalone_backtest_script.py
```

سيقوم السكربت بطباعة ملخص للنتائج في الـ Terminal وحفظ النتائج التفصيلية لكل صفقة في ملف `standalone_backtest_results.csv`.

## 5. النتائج المتوقعة

بعد التشغيل الناجح، ستحصل على مخرجات مشابهة لما يلي (قد تختلف الأرقام قليلاً بناءً على تحديثات البيانات أو إصدارات المكتبات):

```
Starting conversion of egypt_stocks_5yr_data_updated.csv to long format...
Conversion complete. Total rows in long format: [عدد الصفوف]

🚀 Starting Backtest with [عدد نقاط البيانات] data points.
------------------------------------------------------------
✅ Detailed backtest results saved to standalone_backtest_results.csv

--- Backtest Summary ---
Total Trades: 77
Winning Trades: 72
Average PNL per Trade: 30.44%
Win Rate: 93.51%

Note: CAGR and Max Drawdown require a full portfolio simulation with capital management.
This script focuses on per-trade statistics for replication purposes.
```

## 6. ملاحظات هامة لتطابق النتائج

لضمان تطابق النتائج بنسبة 100% مع نظام Manus AI، يجب مراعاة ما يلي:

*   **دقة البيانات:** استخدم نفس ملف `egypt_stocks_5yr_data_updated.csv` بالضبط. أي اختلاف في البيانات (حتى لو كان بسيطاً) سيؤدي إلى نتائج مختلفة.
*   **إصدارات المكتبات:** تأكد من استخدام إصدارات متوافقة من `pandas` و `numpy`.
*   **المنطق البرمجي:** يجب أن يكون الكود المطبق هو نفسه تماماً، بما في ذلك جميع الثوابت (SCORE_MIN, PRICE_GATE_NORMAL, MAX_AVERAGES, إلخ) ومنطق `calculate_swings` و `score_price_position`.
*   **منع الصفقات المتداخلة:** هذا هو العامل الأهم الذي يقلل عدد الصفقات ويجعل النتائج أكثر واقعية. تأكد من أن نظامك لا يفتح صفقة جديدة لنفس السهم إلا بعد إغلاق الصفقة السابقة.
*   **معالجة الأخطاء والقيم المفقودة:** يجب أن يتم التعامل مع القيم المفقودة (NaN) والأخطاء في البيانات بنفس الطريقة (باستخدام `dropna(subset=['Adj Close'])` مثلاً).

باتباع هذه الإرشادات، يمكنك محاكاة أداء نظام Manus AI بدقة عالية والتحقق من فعاليته.
