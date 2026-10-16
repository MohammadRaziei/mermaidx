# یادداشت: `39_mindmap_shapes` روی V8

## وضعیت
- quickjs: ۰ اختلاف با mmdc.
- v8 (mini-racer): ۵۴ اختلاف ساختاری (۱۸ `transform` گره، ۱۷ `d` یال، ۱۷ `data-points`، `viewBox`، `style` ریشه).
  (گزارش ۵ فقط `transform` و عدد ۵۰ را ثبت کرده بود؛ اندازه‌گیری امروز ۵۴ و پنج نوع اختلاف است.)
- در `tests/test_mmdc_structural.py` به‌صورت **strict xfail** ثبت شد (`KNOWN_DIFFERENT[("v8", "39_mindmap_shapes")]`).
  آن تست حالا روی `backend ∈ {quickjs, v8}` پارامتری است. نتیجه: `88 passed, 1 xfailed`.

## علت (اثبات‌شده روی همین نمونه)
1. هر دور خنک‌سازی ی cose-bilkent دو فراخوانی `Math.log(96)` و `Math.log(25)` دارد
   (`Math.log(100*(initialCoolingFactor-finalTemperature)) / Math.log(maxCoolingCycle)`).
   quickjs ۵ دور دارد، V8 ۶ دور. بعد از آن مسیر اجرا فرق می‌کند (اندیس ۱۰۲۲ از ۱۴۰۰ فراخوانی ی `Math`).
2. `Math.sin` ی V8 ی mini-racer در دو فراخوانی ۱ ulp با quickjs و libm ی Python فرق دارد:
   - `sin(-5.969026041820607)`: quickjs/libm `0.3090169943749476`، V8 `0.3090169943749477`
   - `sin(0.5569781975426904)`: quickjs/libm `0.5286235390350444`، V8 `0.5286235390350446`
3. **اثبات علّی (replay):** نتیجه‌ی `Math.*` در V8 با نتیجه‌ی ثبت‌شده‌ی quickjs برای همان ورودی جایگزین شد.
   - همه‌ی تابع‌ها: ۱۴۰۰ فراخوانی (مثل quickjs)، ۰ اختلاف با mmdc.
   - فقط `sin` یا `sin,cos`: ۰ اختلاف.
   - فقط `cos`، `tan`، `atan2` یا `log`: همچنان ۵۴ اختلاف.
   - `atan2` و `tan` هم ۱۸ بار ۱ ulp فرق داشتند ولی روی خروجی اثری نداشتند.
4. `Math.random` علت نیست: هر engine در سه اجرا خروجی یکسان می‌دهد (فقط id های uuid از آن می‌آیند).

## تأییدنشده
- **چرا** `sin` ی mini-racer با quickjs و libm فرق دارد (ورژن V8 یا flag ی build؟) و چرا Chrome (که V8 است) با quickjs برابر است. بررسی نشده.
- فقط روی همین یک نمونه ثابت شده؛ نمونه‌ی دیگر ممکن است به تابع دیگری حساس باشد.
- ران با **کلون GitHub (`b829c08`)** گرفته شد، نه با zip ی کاری؛ اگر چیزی commit نشده باشد ممکن است فرق کند.

## راه حل پیشنهادی (انجام نشده)
`Math.sin` (و در صورت نیاز `cos`) را در shim برای هر دو engine با پیاده‌سازی fdlibm عوض کنیم، با TDD و ground truth ی Chrome.
قبلش بررسی شود V8 ی mini-racer چه نسخه‌ای است. وقتی درست شد، `KNOWN_DIFFERENT` خالی می‌شود (strict xfail خودش خبر می‌دهد).

## روش تکرار (probe؛ چیزی در ریپو عوض نمی‌شود)
1. کپی پکیج در `/tmp/probe/mermaidx` و افزودن یک اسکریپت آخر `context_scripts()` که `Math.sin/cos/tan/atan/atan2/asin/acos/exp/log/hypot/cbrt/tanh...` را می‌پوشاند و `[name, args, result]` ثبت می‌کند، و `__renderLikeMmdc` را طوری می‌پیچد که ردّ را به‌صورت `<!--MT[...]-->` به svg بچسباند.
2. اجرا با `PYTHONPATH=/tmp/probe` (v8 در پروسس فرزند اجرا می‌شود؛ monkeypatch در والد کافی نیست).
3. مقایسه‌ی دو ردّ: اولین اندیسی که نتیجه فرق دارد و اولین اندیسی که خودِ ورودی فرق دارد.
4. replay: جدول `fn|args → result` از ردّ quickjs، و در V8 به‌جای محاسبه‌ی `Math` خوانده می‌شود.

## تله‌های همین کار
- `svg + trace` در quickjs یک string rope می‌سازد و `ctx.eval` خطای `Unknown quickjs tag: -6` می‌دهد. (در پروب با `JSON.parse(JSON.stringify(...))` صاف شد.
  اینکه مسیر عادی ی محصول هم ممکن است به rope بخورد بررسی نشده.)
- `grep` روی `mermaid.js` ی minify شده خروجی عظیم می‌دهد؛ با `-o` و context ی کوتاه بگرد.
- `cd X && cmd &` کل زنجیره را در subshell می‌برد؛ مسیر مطلق بنویس.
