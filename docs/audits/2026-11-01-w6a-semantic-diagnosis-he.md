# M10 / W6a — אבחון אמינות סמנטית

תאריך: 2026-11-01. זהו דוח אבחון, ללא תיקוני מוצר וללא qualification לשחרור.
הסקופ אושר ב־[PROJECT_PLAN.md](../../PROJECT_PLAN.md); W6b דורש אישור נפרד.

## החלטה מומלצת

לשמר את הארכיטקטורה: provider מחזיר `SemanticPlan` יחיד, וה־backend אחראי
ל־authorization, validation, SQL דטרמיניסטי, conformance וביצוע תחת RLS.
הראיות אינן מצדיקות rewrite, repair agent, SQL מהמודל או הרחבת אלגברה כללית.

**התיקון הראשון המוצע ל־W6b הוא זהות חד־משמעית של שדות פלט.** נמצא פגם
דטרמיניסטי שלא דורש ניסוי מודל כדי להוכיחו: התוכנית הקנונית של `hard-005`
מבקשת שני שדות `id`; ה־renderer מחזיר שתי עמודות בעלות אותו שם, וההמרה
למילון מאבדת אחת מהן. יש לתקן זאת לפני שמייחסים את התוצאה למודל או מודדים
איכות Full40. לאחריו מוצעת החלטה נפרדת וממוקדת על זמינות candidates; אין
עדיין ראיה המצדיקה שינוי prompt/model לצורך `medium-009`.

שלוש מסקנות מרכזיות נוספות:

- **F14 שוחזר:** lexical retrieval יכול למנוע ייצוג של שאלה תקינה עוד לפני
  המודל. התופעה רחבה משתי המילים שבאודיט, אך שיעור הכשל במדגם מכוון אינו
  אומדן לאוכלוסיית שאלות משתמשים.
- **F3 הופרד לשלבים:** התוכנית העסקית הנכונה של `medium-009` נתמכת ומחזירה
  תשובה נכונה. תוכנית ידנית המשמיטה את כלל ה־OR משחזרת את מנגנון 11 מול 16;
  זה אינו שחזור של בחירת provider נוכחית. גם בחירת rule נכונה אינה מוכיחה
  שהמודל נמנע מהוספת צמצומים שגויים.
- **F11 הוא בעיקר פער בין encodings נתמכים לבין שקילויות evaluator:**
  `hard-004` עובד גם על fixture לא־ריק עם fanout. חלק מצורות SQL שקולות אינן
  ניתנות לייצוג בתוכנית המאושרת. אין הצדקה לבטל את ההגבלות רק כדי לקבל pass.

## 1. בסיס קפוא ומגבלות ראיות

PR #65 אומת כ־merged; `main` ו־`origin/main` היו
`b1f03a4790c7569f7da0ef8d9be57ddd6da023c5`. ה־head הנבדק של W4/W5 הוא ancestor
שלו ואין ביניהם diff. ענף החקירה נוצר ממנו:
`investigation/m10-w6a-semantic-diagnosis`. שינוי התכנון הראשון: `36591a1`.
הבדלי documentation בהמשך אינם גרסת runtime חדשה.

הזהויות המלאות וגרסאות התלויות נמצאות ב־[baseline.json](w6a/baseline.json),
ונוצרות ללא client או בקשת רשת באמצעות
[freeze_baseline.py](w6a/freeze_baseline.py):

| רכיב | זהות |
| --- | --- |
| Source | `b1f03a4790c7569f7da0ef8d9be57ddd6da023c5`; fingerprint של עץ הקבצים ב־baseline |
| Dataset | `it_operations_v2`, v2, 40 cases; digest `6ac164ab6c58c0b008a65afc01cd26aa434fecd3eaa402b5bdad9c89e6f6540f` |
| Catalog | `it_operations_semantic_catalog`, v3; hash `918df0c63288b7ed7ce700f8442c82bc1ffa3f51e1f4eaa63fd66012af82adb4` |
| Canary | זהות בלבד: v1, digest `83dadd97b819003e9e6aa20b4487affc8a3c926cd7ca3d2672c85225b4ae3fc2`; לא הורץ |
| Provider configuration | shell environment וברירות המחדל בקוד, ללא טעינת dotenv: `gpt-5.6-terra`, reasoning `low`, output 2048, timeout 45s, retries 2; לא נבדקו credentials ולא נשלחה בקשה |
| Provider/runtime | `queryops-provider-runtime-v1`, digest `05564e25cf75eeb63e377e38e216e95e3414243b12fccc7bc17c393c4c5a99c7`; Python 3.13.11, OpenAI SDK 2.46.0, SQLGlot 30.17.0; הרשימה המלאה ב־baseline |
| PostgreSQL | שני clusters נפרדים, 16.14; image ID ב־baseline; migration head `0010_disable_inactive_user` |
| Seed | synthetic `medium`, seed 42, reference `2026-11-01T09:20:36+00:00`; algebra מוסיף fixture מפורש ומבודד |

כל ה־plans בחקירה הוזנו ידנית או נבנו מ־fixtures קיימים. הם בודקים את השלבים
שאחרי הפירוש, ואינם תחליף למודל הפרויקט. **מספר קריאות provider בתשלום: 0**.
גם Mock/fixture אינו ראיית דיוק של מודל אמיתי.

שאילתות actual/baseline בכל זוג רצות באותו snapshot, תחת
`queryops_query_runtime`, read-only ו־repeatable read. הארטיפקטים מתעדים
transaction time, timezone, snapshot, migration ו־fingerprints. זמן SQL הוא
שעון PostgreSQL האמיתי; reference של seed אינו מקפיא `CURRENT_TIMESTAMP`.
לכן בהרצה בתאריך אחר יש לשמר את ההבחנה בין תוצאה עסקית שקולה לבין מספרי
הרשומות ההיסטוריים, ולבנות contrasts בעלי מרווח מתאים מגבולות הזמן.

ה־Canary מהאודיט באוקטובר השתמש ב־`gpt-5.6-luna`, source `2d7796c` ו־environment
ישן. הוא תיעד 9/10 ו־`required_rule_missing` ב־`medium-009`. זו ראיה היסטורית
בלבד להתנהגות אותו מודל/ריצה; W5 שינה identity/transport, ולא הופך אותה
לראיה כשירה עבור הבסיס הנוכחי. השוואת Git מאשרת ש־catalog, dataset,
grounding, plan validation, renderer ו־conformance הרלוונטיים לא השתנו מאז;
שינויים ב־provider telemetry וב־top-N scoring אינם הוכחת תיקון משמעות השאלה.

## 2. שיטה, הפרדת שלבים וחלוקת עבודה

| אחראי | גבול הבדיקה | ארטיפקטים |
| --- | --- | --- |
| Agent A | candidate/catalog coverage, הקשר מורשה, vocabulary ו־counterexamples; ללא DB/provider | [corpus](w6a/candidate-cases.json), [probe](w6a/candidate_probe.py), [results](w6a/candidate-results.json) |
| Agent B | business composition דרך `QueryEngineService`, SQL/RLS, output ו־scoring; DB ייעודי 55447 | [probe](w6a/composition_probe.py), [results](w6a/composition-results.json) |
| Agent C | algebra, grain, renderer/conformance ו־result/semantic comparisons בנפרד; DB ייעודי 55448 | [probe](w6a/algebra_probe.py), [results](w6a/algebra-results.json) |
| Coordinating agent | אימות prerequisite, identities, בדיקות משותפות, בחינת הסברים סותרים והמלצה | דוח זה, baseline והפניות לבדיקות קיימות |

ארטיפקטי התוצאות מכילים counts, מזהי הגדרות, hashes וסיבות כשל בטוחות;
אין בהם raw result rows, provider payloads, credentials או baseline answers.
קוד ה־probes מפנה להגדרות evaluator הקיימות ללא שינוי בהן. SQL witnesses
ל־plans שנדחו מסומנים במפורש: הם מבודדים שקילות downstream, ואינם מסלול
מוצר שעוקף validation או הוכחה ש־plan נדחה הוא נתמך.

סיווגים בדוח: **שוחזר** — בקוד ובגבול המצוין; **היסטורי בלבד** — תצפית
מתועדת מהאודיט; **מוסק** — מסקנה מתאימה לראיות אך ללא בדיקה מלאה;
**לא אומת** — אין ראיה מספקת. כשל אבחון צפוי אינו כשל של סקריפט: הסקריפטים
כוללים assertions על התוצאות החיוביות והשליליות הצפויות.

## 3. מטריצת כיסוי וכשל

| בדיקה | תוצאה | מקור הכשל / מה הוכח | סיווג |
| --- | --- | --- | --- |
| 11 canonical entity families | כולן נשלפות | קיים מסלול תקין; אין חסימת catalog כללית | שוחזר, projection בלבד |
| `devices` / `endpoints` מול `computers` / `laptops` / `desktops` / `servers` | שתי הראשונות עוברות; ארבע האחרונות מחמיצות devices | lexical/structural retrieval; לא מדידת provider | שוחזר |
| 79 exploratory candidate cases | 69 positives, 10 controls; 40/69 מכילות את כל ה־IDs הצפויים; 27 entity misses ו־2 definition-context misses; 10/10 controls | מדגם stress מכוון עם expectations מחקריים; אינו מדד דיוק V2 או recall באוכלוסייה | שוחזר |
| `software subscriptions` / `allocated software seats` | software_installs מופיעה בלי ישות licenses/assignments המצופה | misleading anchors; הפירוש העסקי האפשרי מתועד, precision לא נמדד | שוחזר בגבול hypothesis |
| concept של entity שהוסף כ־connector | עצם הימצאות entity אינה מבטיחה זמינות ההגדרה העסקית | candidate definition/context closure | שוחזר; ההמלצה אינה blanket closure |
| `medium009_intended_or` | 16/16; validation/render/conformance/result/semantic עברו | תוכנית נכונה נתמכת | שוחזר ב־PG, plan ידני |
| `medium009_status_only` | 11/16; ביצוע הצליח, result incorrect, `required_rule_missing` | פירוש/בחירת הגדרה יכולה ליצור תשובה חלקית מבחינה עסקית; אינה truncation | מנגנון שוחזר; בחירת מודל נוכחית לא אומתה |
| `medium009_or_plus_status` | 11/16; `rules_correct=true`, comparison incorrect | selected-rule check אינו oracle לכוונת NL; AND נוסף מצמצם כדין SQL | שוחזר |
| `medium009_no_distinct` | 25 rows / 16 unique מול 16 | grain/planner encoding; DISTINCT של פירוט נחוץ ב־join עם installs | שוחזר; אינו הסבר לכשל ההיסטורי |
| service-account / terminated-active canonical | 11/11 ו־4/4 | הגדרות מורכבות אחרות עובדות | שוחזר, counter-evidence |
| `hard005` canonical | SQL columns `id,id`, dictionary מחזיק מפתח אחד; provenance `output_name_duplicated` | deterministic output identity/delivery; לא כשל provider | שוחזר, פגם מוצר |
| `medium006` שלוש צורות קנוניות | 8/8 בכל צורה; semantic/result עברו | PK/name variants הנתמכים עובדים | שוחזר |
| `hard004` שתי צורות מפתח קנוניות | 1/1, nonvacuous; semantic/result עברו | נתמך; שתי memberships מאתגרות count fanout | שוחזר |
| `hard004` count ללא DISTINCT, גם עם SELECT DISTINCT | 2 מול 1; evaluator דוחה | SELECT DISTINCT אינו מתקן COUNT שגוי בתוך קבוצה | שוחזר |
| grouping נוסף, dependent/equal, שאינו projected | `group_by_incomplete`; SQL witness שקול מתקבל ב־evaluator | supported-encoding restriction; לא חוסר יכולת לענות על המקרה | שוחזר |
| hidden group keys ללא output fields | runtime מקבל, evaluator דוחה missing grain/output | אין bypass של qualification רק משום שה־SQL חוקי | שוחזר |
| outer join לעומת INNER identity | runtime יכול לבצע; comparator עשוי לדחות למרות ערכים שווים במדגם | הוכחת equivalence מוגבלת במכוון ליחסי INNER; שוויון במדגם אינו זהות כללית | שוחזר |
| `SUM(DISTINCT ...)` | `sum_distinct_unsupported` | בקשה/encoding מחוץ לאלגברה; hard006 קנוני עובד | שוחזר |
| grouped empty מול scalar empty | SQL witness מחזיר 0 מול 1 שורות | הבדל SQL אמיתי; ה־plans הספציפיים נדחו כבר כ־`predicate_contradiction` | שוחזר כ־SQL witness בלבד |

המזהים המלאים, פרטי הבדיקה וה־counts הם בארטיפקטים; hashes של results אינם
oracle חוצה aliases: שני outputs שקולים בעלי שמות מפתחות שונים יכולים להפיק
hash שונה ולהיות מוכרעים כשקולים באמצעות provenance. אין להסיק שקילות רק
ממספר שורות שווה, ולא מכשל hash בלבד.

## 4. ממצאי שורש והסברים מתחרים

### D1 — התנגשות שמות פלט מאבדת מידע (P1, ביטחון גבוה)

`hard-005` דורש במפורש `devices.id` ו־`directory_users.id`; baseline מגדיר
`device_id` ו־`user_id`. `sql_renderer.py::_render_select_items` מציג fieldrefs
ללא alias. `sql_executor.py::_execute_statement` לוקח את `result.keys()` ואז
`dict(row)` מתוך mappings, ולכן `id` אחד דורס את השני. ה־probe השווה באותו
snapshot גם את ערכי שתי העמודות ברמת tuples ואישר שהם שונים באמצעות boolean
בלבד; אין שימור או חשיפה של הערכים.

Plan validation, SQL safety ו־self-conformance עוברים כי הם בודקים משמעות
של SQL ושדות, ולא מזרק חד־חד־ערכי מ־field identity למפתח JSON. extractor
ב־`evaluation/provenance.py` דוחה את שמות הפלט הכפולים; במצב זה ההשוואה נשארת
`unestablished`. זו תגובה שמרנית של evaluator לאובדן מידע ממשי.

הסבר חלופי של FK-equivalent output נבדק: אפשר להפיק שמות ייחודיים באמצעות
שדות FK אחרים, אבל scorer הקבוע דוחה את grain/output החלופי. זה אינו תיקון
לתוכנית הנדרשת, ואין לשנות את contract כדי להכשיר workaround. `SemanticPlan`
גם אינו מספק alias חופשי למודל; עדיף שה־backend יפיק שמות דטרמיניסטיים.

השפעה: מידע יכול להיעלם מ־result JSON ומצרכניו גם כאשר SQL החזיר אותו.
הפגם עצמאי מפירוש שפה, ולכן הוא מועמד טוב יותר לתיקון הראשון משינוי model.
לא בוצע browser/CSV replay של התרחיש; התפשטות הכשל מעבר ל־executor מוסקת
מהחוזה ואינה מוצגת כאן כשחזור UI.

### D2 — Candidate availability היא חסימה נפרדת מפירוש (P2, ביטחון גבוה בגבול)

`semantic_grounding.py::_build_candidate_context` בונה קודם eligible catalog
לפי schema/columns מורשים, ואז מסנן lexical/structural candidates ומוסיף
relationship connectors. `semantic_plan.py:254–273` מחייב IDs מתוך projection.
לכן provider אינו יכול לתקן בחירה של entity חסרה רק משום שהטבלה קיימת
ב־schema. ההחמצות לא נגרמו מהיעדר הרשאה ב־positive fixtures.

ב־69 positive cases כל ה־IDs הצפויים קיימים ומורשים ב־catalog; ה־projection
מכסה 56/91 expected entity occurrences, 30/40 concept occurrences, 7/13
relationships, 3/6 rules ו־3/3 metrics. אלה denominators נפרדים; אין לחברם
למדד answer accuracy. בתוך 38 vocabulary cases הכיסוי הוא 20/38; canonical
cases כולם עוברים ולפחות החמצה אחת מופיעה ב־10 מתוך 11 משפחות במדגם.

Counter-evidence: `managed server inventory` כן נעזר ב־description fallback;
קיימים canonical/entity/metric/composition paths תקינים; negation, decoys,
no-permission/no-scope, non-queryable resources ועמודות חסרות נבדקו ב־10 controls.
אלה בדיקות projection עם seam למטא־דאטה לא־persisted, **לא הוכחת RLS**.
חלק מהפרפרזות עמומות ונשארות hypotheses מסומנים; אין מדידת precision מלאה.

### D3 — בחירת OR אינה שקולה להבטחת כוונת המשתמש (P1 איכות, attribution מוגבל)

הגדרת `non_compliant_device_posture` היא OR של compliance, antivirus ו־encryption,
יחד עם outdated install כ־AND. היא זמינה עבור שאלת `medium-009` המקורית.
ה־renderer/conformance מממשים אותה נכון. השמטת ה־rule ובחירת
`non_compliant_device` בלבד משחזרת 11 מול 16. הוספת ענף אחד כ־concept לצד rule
משאירה `rules_correct=true`, אך מצמצמת ל־11, 9 או 4; evaluator התוצאה מזהה זאת.

זהו counterexample להסתמכות בלעדית על presence של selected rule. בייצור NL
אינו Required Intent מהימן; backend אינו אמור לנחש שה־AND נוסף אסור כאשר
משתמש באמת ביקש צמצום. אין להחזיר parser באנגלית כסמכות עסקית שנייה.

ה־prompt הנוכחי כבר מסביר OR rule לעומת top-level AND וכולל דוגמה גנרית
של base request ונרמול עצמאי. לכן "להוסיף שוב הוראת OR" אינה המלצה מבוססת.
לא נבדקה תדירות הכשל כיום, ההשפעה של context על המודל או יתרון של model אחר.
התקלה ההיסטורית תואמת מנגנון selection, אך current provider attribution
נשאר **לא מאומת**. אין כאן ראיה לכשל SQL renderer במקרה הזה.

ב־inactive-directory-user contrast היו 26 משתמשים עם login ישן ואפס בעלי
`last_login_at IS NULL` בתוך ה־Scope שנבדק. ענף הזמן נבדק; חיובית, ענף NULL
נשאר לא מאומת בחקירה זו. בדיקת catalog/SQL אינה מחליפה fixture שמחזיר NULL.

### D4 — תמיכה קנונית קיימת; broad algebra expansion אינו מוצדק (P2)

`semantic_plan.py:435–443` מחייב set equality בין `output_fields` ל־`group_by`
כאשר שניהם קיימים בתוכנית aggregate. המגבלה אכן דוחה hidden dependent/equal
group keys שה־evaluator יכול להוכיח כשקולים. היעדר projected keys בכלל הוא
מסלול אחר: SQL נתמך, אך grain/output לא עומדים בחוזה evaluator.

ה־evaluator מבדיל בין semantic contract, result equivalence ו־literal structural
diagnostic. לדוגמה, name projected/PK grouped נותן SQL result שקול במדגם אך
נכשל בבדיקת grain הקבועה. זה מצביע על גבולות הוכחה/encoding; אין ראיה שיש
להכשיר כל צורה חוקית ב־PostgreSQL. INNER FK/unique identity אינו מתרחב אוטומטית
ל־LEFT JOIN. count fanout ו־extra population dimensions נדחים כראוי.

לא נמצא בניסויים אלה false-positive מוכח של result comparator או defect חדש
ב־renderer של aggregation. לא כל יכולת SQL היא דרישת מוצר V1. תוכנית שמשתמשת
ב־`SUM(DISTINCT)` היא encoding לא נתמך; מענה product-equivalent קנוני נבדק
ל־hard006. בקשה שאינה ניתנת לייצוג כלל צריכה clarification/unsupported בטוח,
ולא relaxation של checks.

## 5. חלופות והיקף W6b המוצע

| חלופה | יתרון | חסרון / ראיה נגדית | המלצה |
| --- | --- | --- | --- |
| תיקון output identity דטרמיניסטי | פגם מוכח, בדיקה ללא provider, שומר שתי זהויות וראיות evaluator | יש לסקור aliases, aggregation collisions, API/cards/CSV ו־SQL שמור | **W6b ראשון, קטן ומוגדר** |
| להוסיף `computer`/`laptop` ועוד aliases נקודתיים | שינוי catalog קטן | החמצות ב־10/11 משפחות; synonym list אינסופית אינה פותרת context closure | אפשרות מוגבלת בלבד, לא פתרון כללי |
| להפוך entities/relationships מורשים לזמינים תוך שמירת ranking לא־מחייב | מנצל schema מורשה שכבר קיים ומפריד availability מ־lexical selection | בניסוי copy-only שיפר 40→60/69; לא פותר definitions חסרות ולא מוכיח selection טוב | החלטה ממוקדת לאחר D1; להוכיח budget ו־negative controls לפני מימוש |
| לחשוף את כל catalog | מפחית retrieval misses | minimal full projection הוא 18,366 bytes מול cap 16,000, עוד לפני examples/signals | לא drop-in בטוח |
| להוסיף אוטומטית כל definition של כל connector | עשוי לפתור חלק מהחמצות | copy-only: 14/69 overflows עד 20,655 bytes; context ambiguity לא נמדד | לדחות blanket closure |
| שינוי prompt/model | עשוי לשפר composition | הוראת OR קיימת; אין current live comparison; לא יתקן JSON key loss | רק אחרי אבחון מבוקר מאושר |
| הרחבת GROUP BY / generic canonicalizer | מקבלת יותר SQL-equivalent encodings | canonical cases עובדים; מורכבות בהוכחות grain/FK/fanout/outer join | לדחות עד ראיית blocker אמיתי |
| repair calls / binding English parser | מסלול תיקון נוסף | מוסיף סמכות/קריאות/מורכבות ושובר את ההחלטה הארכיטקטונית | לא מומלץ |

ניסויי alternatives של Agent A היו **copy-only exploratory simulations**, ללא
שינוי pipeline. הוספת כל entities/relationships המורשים תוך שימור definitions
הנוכחיים נכנסה ל־budget בכל 69 המקרים: 7,064–14,521 bytes. זה אינו upper bound
לכל שאלה עתידית או הבטחת איכות provider. widening של definitions הנוכחיים
לכל connectors כיסה raw 42/69, אבל רק 55/69 projections נכנסו ל־budget ורק
28 היו גם covered וגם fit. אין להסיק שיותר context תמיד טוב יותר.

### Acceptance לתיקון הראשון המוצע

מטרה: mapping דטרמיניסטי, ייחודי ויציב בין שדות פלט ל־JSON columns, ללא alias
חופשי מה־provider וללא שינוי semantics של ה־SQL.

1. `hard-005` הקבוע מחזיר שתי זהויות נפרדות עם שמות ייחודיים; ערכי device/user
   שונים נשמרים. semantic contract, provenance ו־result comparison עוברים על PG.
2. מקרים כלליים: שני `id`, שני `name`, collision בין field label ל־aggregation
   ID, סדר שדות משתנה ושמות ייחודיים קיימים. אין hard-code ל־case/table pair.
3. שאילתות עם שמות פלט ייחודיים שומרות תאימות ככל האפשר. הגדרת alias היא
   עניין backend; אין שינוי datasets, thresholds, Required Intent או policy.
4. לבדוק conformance/provenance/order mappings וצרכני query→save→refresh→table/
   visualization→CSV. SQL שמור בעל labels עמומים אינו רשאי להמשיך לאבד מידע
   בשקט; לבחור טיפול מפורש ובטוח לפי גבול השינוי, בלי migration של raw rows.
5. השוואות result/semantic נפרדות, fanout/NULL/empty fixtures, אין שינוי RLS,
   current-viewer authorization, caps, CSV sanitization או evaluator-only isolation.
6. regression נכשל על baseline ועובר אחרי התיקון; focused backend+PG+API,
   frontend/browser רק בגבולות הצרכנים שהשתנו, וסקירה עצמאית של ה־diff.

היקף צפוי S–M / V3 לפי גבול החוזים. אין לכלול באותו PR prompt/model tuning,
general GROUP BY expansion, synonyms sweep או תיקוני W7–W9. לאחריו יש לבקש
החלטה צרה על D2; שיפור F3 דורש ראיית provider נוספת ולא יעד pass מלאכותי.

### Regression מול held-out

ה־79 שאלות וה־plans החדשים בדוח הם **exploratory diagnostics**. המחברים ראו
את ה־catalog והתוצאות; אין כאן blind held-out score. גם תרחיש שנכתב לפני
הרצת probe אינו נעשה אוטומטית validation עצמאי.

ל־W6b: להשאיר את V2 ואת corpus האבחון כ־regressions ידועים. reviewer שלא כתב
את התיקון יכין לפני האימות contrasts חדשים של collisions, FK identities,
NULL/fanout ו־paraphrases, בלי להשתמש בתוצאותיהם לתכנון השינוי. להקפיא hash,
source/config וקריטריונים לפני חשיפה למממש. כשל חוזר לאבחון, והסט שנחשף כבר
אינו held-out בסבב הבא. ל־W6c יידרשו גם ניסוחי composition/selection חדשים
ובדיקה נפרדת עם מודל הפרויקט באישור מפורש.

## 6. ניסוי provider אפשרי — דורש אישור נפרד

אין צורך בתשלום כדי להצדיק את D1 או לשחזר את D2. אם נדרשת הכרעה על F3 לפני
שינוי prompt/context, מוצע ניסוי אבחוני בלבד אחרי תיקון ה־output:

- מודל יחיד `gpt-5.6-terra`, reasoning `low`, 2048 output tokens, 45s, retries 2,
  official endpoint בלבד; runtime identity/manifest חדש לפי source והתלויות בפועל.
- לכל היותר **8 logical calls**, עד **24 HTTP attempts** לפי retry policy, ללא
  repair/fallback/הרחבה אוטומטית. הגבול הוא 2048 output tokens לכל attempt;
  שמונה responses מצליחים הם עד 16,384, אך retries שנצרכו/חויבו יכולים להוסיף
  usage. אין כאן תקרת חיוב כספית מאומתת או הנחה שכשל transport היה חינם.
- שמונה המקרים המוצעים מפורטים בטבלה להלן. אלה diagnostics גלויים, לא held-out.
  שינוי בנוסחים או בתקציב יחייב הצעת ניסוי חדשה לפני אישור; אין קריאות qualification.
- diagnostic value: candidate availability לעומת בחירה בפועל, extra narrowing,
  DISTINCT/grain ו־supported canonical plans. לשמור רק safe stage evidence,
  model/config identity ו־usage; לעצור בכשל auth/config/fatal, ללא retries ידניים.
- 8 קריאות אינן אומדן יציבות או שיעור כשל. אין יתרון model מוכח ואין authorization
  לבצע את ההצעה הזאת במסגרת W6a.

| מזהה ניסוי מוצע | Question קפוא לצורך בקשת אישור עתידית |
| --- | --- |
| P1 / medium-009 | Show distinct non-compliant devices that have outdated software. |
| P2 / base OR paraphrase | List distinct devices with outdated software that meet our non-compliant device posture definition. |
| P3 / base OR paraphrase | Which distinct devices have outdated software and are non-compliant by device posture? |
| P4 / independent narrowing | Show distinct non-compliant devices with outdated software, restricted to devices whose compliance status is non_compliant. |
| P5 / hard-004 | Which privileged-group users had more than 5 failed logins in the last 30 days? |
| P6 / hard-005 | Which devices assigned to inactive users have unsupported high-risk software? |
| P7 / entity recall | How many computers do we manage? |
| P8 / entity plus subtype | Count all company laptops. |

P2–P4 נוסחו לאחר האבחון לצורך ניסוי עתידי בלבד. ה־held-out העצמאי שתואר
לעיל צריך להשתמש במקרים אחרים. טבלת שאלות זו אינה נשלחת ל־provider ב־W6a.

## 7. שחזור ואימות

### ללא PostgreSQL

מה־repository root, עם סביבת backend הקיימת:

```bash
cd backend
PYTHONPATH=. .venv/bin/python ../docs/audits/w6a/freeze_baseline.py > /tmp/w6a-baseline.json
PYTHONPATH=. .venv/bin/python ../docs/audits/w6a/candidate_probe.py
```

הפקודה השנייה כותבת את קובץ candidate-results לצד הסקריפט. לשחזור read-only
של checkout יש להריץ בעותק זמני או לשמור את תוצר ההרצה לפני השוואה; אין צורך
לשנות production. ה־source guard מונע הצגת תוצאות כנגד runtime ששונה בשקט.

### PostgreSQL מבודד

יש ליצור **שני containers חדשים** עם `postgres:16.14`, bind מקומי בלבד,
ללא volumes או DB של האפליקציה. שמות/ports של החקירה מפורשים בסקריפטים:
composition ב־55447 / `queryops_w6a_composition_test`; algebra ב־55448 /
`queryops_w6a_algebra_test`. אין להחליף אותם ב־DB רגיל כדי לעבור guard.
ה־user הוא `queryops`; לבחור password סינתטי disposable, ללא secret אמיתי.

לכל cluster להגדיר, עם פרטי הסביבה החדשה בלבד:

```bash
export DATABASE_URL='postgresql+psycopg://queryops:<disposable-password>@127.0.0.1:<port>/queryops'
export POSTGRES_TEST_DATABASE_URL='postgresql+psycopg://queryops:<disposable-password>@127.0.0.1:<port>/<disposable-test-db>'
export POSTGRES_TEST_DATABASE_DISPOSABLE=1
```

`--initialize` מותר על DB חדש וריק בלבד; מריץ migrations ו־medium seed קבוע.
אין להריץ אותו על תוצר חקירה שכבר קיים. פקודות מ־`backend/`:

```bash
# composition environment, port 55447
PYTHONPATH=. .venv/bin/python ../docs/audits/w6a/composition_probe.py --initialize --out /tmp/w6a-composition.json
# algebra environment, port 55448
PYTHONPATH=.:tests .venv/bin/python ../docs/audits/w6a/algebra_probe.py --initialize --add-contrast-fixture --out /tmp/w6a-algebra.json
```

להרצה חוזרת על אותם fixtures, להשמיט `--initialize` ו־`--add-contrast-fixture`.
algebra מוסיף שני users, שתי privileged groups, שתי memberships לכל user,
6 לעומת 5 failed events עדכניים ועוד old/success negatives. כך `hard-004`
אינו pass ריק: אדם אחד צריך להיכלל, ו־count ללא DISTINCT מכניס שניים.

### ראיות בדיקה

- 13 קבצי semantics/grounding/ownership/render/conformance/scoring/evidence/
  provenance: **480 passed, 7 skipped** ללא משתני PostgreSQL; הסיבות הן בדיוק
  בדיקות PG ב־`test_relational_semantics.py`.
- אותו קובץ על cluster מבודד: **33 passed, 0 skipped**. אין לחבר את המספרים
  כאילו כל test case שונה; חלק מהבדיקות חוזרות בשתי הריצות.
- 79 candidate cases, 18 composition probes ו־19 algebra probes כוללים assertions
  לתוצאות הצפויות; negative diagnostics אינם "tests failing".
- בדיקת diff/source guard מאשרת שלא שונו implementation, tests, prompts,
  catalog, frozen datasets, baselines או release gates.
- Coordinator הריץ מחדש את 79 candidate cases, את 18 composition probes ואת
  19 algebra probes; assertions עברו. קובצי ה־PG החוזרים נשמרו ב־`/tmp/queryops-w6a/`
  כדי לשמר את הראיה המקורית. Ruff לכל ארבעת הסקריפטים, compileall, diff-check
  ובדיקת קישורי Markdown מקומיים עברו. סקירה עצמאית מתועדת בסעיף הבא.

לא הורצו paid provider calls, qualifying canaries/Full40, browser release QA או
בדיקות production/shared deployment. אין שינוי UI/implementation בענף הזה;
ממצאי ה־UI/CSV של D1 דורשים verification במסגרת תיקון W6b, ואינם מוצגים
כבר כראיית browser. אין מסקנה של V1 readiness.

## 8. סקירה עצמאית, סטטוס והחלטה הבאה

סטטוס עריכה: consolidation לפני סקירה עצמאית. סעיף זה יעודכן בתוצאות reviewer
בלתי תלוי, תיקוני ראיות אם נדרשו, וסטטוס Git/PR האמיתי לפני handoff.

החלטה נדרשת לאחר review: לאשר רק את תיקון output identity שתואר לעיל כצעד
W6b ראשון. Candidate availability, current provider composition ואפשרות
להרחבת supported algebra נשארים החלטות נפרדות לפי סדר הראיות; אין כאן אישור
מובלע ליישם אותן. W7–W9 ו־W6c נשארים נדרשים בדרך ל־V1, והפרויקט אינו released.
