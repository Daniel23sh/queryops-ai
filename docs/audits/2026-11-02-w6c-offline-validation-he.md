# M10 W6c — אימות סמנטי עצמאי, שלב offline

## החלטה והיקף הראיה

השלב ה־offline הושלם על runtime של `main` ב־
`92bf4ca8b7df1d591cdb1b5f3e66188e19cdb5f0`. PR #68 אומת כ־merged ב־
2026-11-02T08:57:17Z, וה־merge הוא latest main בעת תחילת הבדיקה. הענף
`codex/m10-w6c-offline-validation` התחיל מעץ נקי. מקור המוצר, prompts,
catalog, V2, thresholds ו־CI לא שונו. כל תוכניות העדות ידניות; מספר קריאות
ספק בתשלום: **0**. פירוש ספק ודיוק תשובות לשפה טבעית נשארים **לא נמדדים**.

זמינות המועמדים וזהות הפלט שהוספו ב־W6b עמדו במקרים החדשים שנבדקו.
קיימת מגבלת encoding באוכלוסיית OR עם שני ענפי קיום אופציונליים, ופילטר
מיותר אחד נותר בלתי מובחן ב־fixture. לכן אין כאן הוכחה לאמינות סמנטית מלאה,
השלמת W6c החי, readiness או qualification של V1.

## שלמות ה־held-out והזהויות

- [20 שאלות וקריטריונים](w6c/heldout-v1.json) נכתבו בידי agent בהקשר חדש,
  שלא כתב את תיקוני W6b ולא הריץ product/candidates/tests/provider לפני הכתיבה.
  הוא ראה catalog, schema וחוזי Evaluation, וכן prefix קטן של V2 ודוגמאות catalog;
  אין טענה לעיוורון לכל דוגמאות הדומיין. אין שימוש בשאלות אלה כ־dataset מוצר.
- השאלות הוקפאו ב־`e22831e` לפני הרצה; raw SHA256:
  `ed5946c1f837b344563ef770b687e83ed1e6cce182a42820b9e2e7df9d4e8b8a`.
- [תוכניות ו־SQL oracle עצמאיים](w6c/witnesses.py), [fixture](w6c/fixture.py)
  ו־[manifest](w6c/freeze.json) הוקפאו בנפרד ב־`97ef82b`, לפני ההרצה הראשונה.
  hashes של השאלות, התוכניות וה־fixture לא השתנו אחרי תצפית בתוצאות.
- 14 ציפיות success, שלוש clarification ושלוש denied. שני IDs חולקים אותה
  שאלה בכוונה, עם scope context שונה. חמשת ההקשרים הם דרישות fixture מפורשות.
- לא נמצאה חפיפה מדויקת לאחר נרמול עם 79 שאלות W6a או 32 שאלות הסוקר של
  PR #68. משפחות הסמנטיקה קשורות מטבען; ניסוח חדש אינו מדד generalization.
  CA-B01 וכל W6a מסומנים בנפרד כרגרסיות מוכרות. הסט החדש שנחשף כעת אינו
  יכול לשמש שוב כ־unseen בסבב tuning עתידי.
- V2 digest נשמר `6ac164ab6c58c0b008a65afc01cd26aa434fecd3eaa402b5bdad9c89e6f6540f`;
  catalog v3 נשמר `918df0c63288b7ed7ce700f8442c82bc1ffa3f51e1f4eaa63fd66012af82adb4`.
  ה־probe משווה אותם ואת מקור runtime לפני בניית engine או initialization.

## שיטה והפרדת שלבים

[probe.py](w6c/probe.py) משתמש ב־schema context האמיתי של analyst בעל scope
משויך, במועמדים האמיתיים וב־validator/renderer/conformance/executor הקיימים.
הוא אינו מחליף projection חסר בקטלוג מלא. חוזי ההשוואה החדשים נוצרים בזיכרון
רק לצורכי audit; שום חוזה/שאלה/תשובה קפואה של Evaluation V2 לא נערכו.

PostgreSQL 16.14 רץ ב־container חדש עם loopback בלבד, port 55469 ו־DB
`queryops_w6c_test`. initialization מותר רק על schema ציבורי ריק, תחת guard
של disposable DB ובדיקה קשיחה של host/port/name. seed קטן דטרמיניסטי 42 עם
reference `2026-11-02T09:00:00+00:00`, בתוספת contrasts סינתטיים קפואים.
זמן PostgreSQL הוא זמן הטרנזקציה האמיתי; המקרים החדשים רחוקים מגבולות הזמן.
ה־fixture הזה אינו סביבת qualification מסוג medium לפי חוזה release.
שני ה־containers השתמשו ב־image ID
`sha256:e013e867e712fec275706a6c51c966f0bb0c93cfa8f51000f85a15f9865a28cb`.

לכל מקרה actual/oracle/ניגודים חולקים טרנזקציית `REPEATABLE READ`, UTC,
read-only, `queryops_query_runtime` ו־RLS עם ההרשאות המשויכות. SQL oracle עובר
את אותו validator ו־executor. השוואה משתמשת ב־`observed_evidence_side`, provenance
וה־scorer הקיימים; לא מסמנים completeness ללא בדיקתה. נשמרים רק counts,
statuses, hashes, output labels ו־runtime metadata; rows וערכי מזהים נשארים
בזיכרון זמני בלבד. DB fingerprint, גרסאות תלויות ו־migration
`0010_disable_inactive_user` מופיעים ב־[results.json](w6c/results.json).

סיווגים בכל ארטיפקט: **reproduced** — רגרסיה מוכרת ששוחזרה;
**independently_verified** — תצפית offline ישירה; **inferred** — קריטריון השפה
או הסקת גבול שלא נמדדו במלואם; **unmeasured** — provider/דיוק NL או שלב שלא
הורץ. `correct` על תוכנית ידנית מתאר התאמה ל־oracle, ולא בחירת תוכנית משאלה.

## תוצאות לפי שלב

| שלב | ראיה עצמאית | מה נשאר פתוח |
| --- | --- | --- |
| request permission | W6C-017 נדחה ב־`forbidden` לפני projection/provider | זהו gate משותף; לא ריצת HTTP חדשה |
| candidates | 19/19 projections כוללים את יעדי ה־coverage; 15,750–15,995 bytes, closure/columns/determinism עברו | אין בחירת ספק; 19 כולל controls עם יעדים מורשים חלקיים |
| resource/column eligibility | licenses חסר אינו חוזר כ־connector; hidden cost בפלט וב־SUM נדחה; audit entity ו־CVE מומצא נדחים | hidden cost הוא seam של allowed_columns, לא field ACL מתמשך חדש |
| plan expressibility | 13/14 תוכניות חיוביות התקבלו; W6C-007 נדחה | מגבלת LEFT orientation מפורטת בהמשך |
| render/safety/conformance | כל 28 תוכניות/ניגודים שהתקבלו רונדרו דטרמיניסטית ועברו safety/conformance | תוכנית שגויה לכוונת NL עדיין יכולה להתממש בדיוק |
| conformance adversary | הסרת WHERE מתוכנית חיובית בעלת predicates נדחתה | לא הוכחה לכל שינוי SQL אפשרי |
| PostgreSQL/oracle | 13/14 תוכניות חיוביות נתנו `correct` עם evidence שלם; ה־14 לא הגיעה לביצוע | לא answer accuracy של provider |
| semantic/result negatives | 14/16 ניגודים שגויים נתנו `incorrect`, אחד נחסם ב־overconstraint; אחד נתן `correct` | ה־fixture אינו מבדיל כל תוכנית שגויה |
| output identity | W6C-010 החזיר 5 רשומות עם `devices__id` ו־`software_installs__id`, ערכים שונים נשמרו | צרכני UI/CSV נשענים כאן על רגרסיות W6b הקיימות |
| scope/RLS | fixtures תואמים ב־Finance נעדרו מתוצאות device של analyst; snapshots/role/read-only אומתו | לא בדיקת כל צירופי ההרשאות האפשריים |
| provider interpretation / NL answer accuracy | **unmeasured**, 0 קריאות | דורש החלטת ניסוי נפרדת |

W6C-002/003 הם קריטריוני clarification מוסקים; אין טענה שה־backend בוחר
clarification מתוך האנגלית. W6C-003 מוכיח רק דחיית עמודת CVE מומצאת.
W6C-016 משנה במכוון את `scope_reference_resolved` בהקשר סינתטי, בעוד metadata
מורשה נשמר; אין מכאן הוכחה שהקשר לא עקבי כזה נוצר בנתיב ה־HTTP הרגיל או
ש־validator לבדו יכול לפענח את הביטוי "my authorized area".
במקרה זה נבדק projection בלבד: לא הורצה תוכנית עם flag לא פתור, ולא הורץ
מסלול clarification. ציפיית ה־clarification נשארת inferred.

## ממצאים וגבולות שלא נפתרו

### F1 — אוכלוסיית OR אופציונלית אינה מיוצגת בעץ שנבדק

**Independently verified:** W6C-007 מבקש inactive human on-leave עם privileged
membership **או** critical unresolved user event, כולל מי שיש לו רק ענף אחד.
כל המועמדים והתלויות זמינים, וה־oracle העצמאי החזיר 3 משתמשים, כולל exclusive
branch fixtures. תוכנית ה־LEFT הידנית נדחית ב־`left_join_orientation_unsupported`.

נבדקו כל שמונת צירופי INNER/LEFT באותו עץ בן שלושה relationships. שניים
נדחו; שישה התקבלו, עברו conformance וביצוע, וכל אחד החזיר 1 מול 3, עם multiset
שונה. הקוד ב־`backend/app/query_engine/relational_semantics.py:14` משמר ב־LEFT
רק `from_entity`; ה־catalog מפנה membership ו־security_event אל user. זו מגבלת
ייצוג/כיווניות קיימת, לפני בחירת ספק; לא renderer defect ולא regression מוכח של W6b.

**Inferred:** הוספת EXISTS/UNION או reverse LEFT עשויה לאפשר את הסמנטיקה, אך
לא נוסתה ואינה מאושרת. האימות ממצה את העץ הנבחר בלבד; הוא אינו הוכחת אי־אפשרות
לכל תוכנית שניתן להעלות על הדעת בכל הגרף. נדרשת החלטת V1 נפרדת: הצעת תיקון
תחומה או גבול מוצר מפורש של unsupported/clarification. ספק חי אינו פותר encoding חסר.

### F2 — פילטר מיותר שאינו משנה את התוצאה ב־fixture

**Independently verified:** ב־W6C-005, הוספת `is_exception=false` לבקשה הכוללת
כל active mandatory assignment היא שגויה לפי הקריטריון הקפוא. היא התקבלה,
עברה conformance, semantic score והשוואת תוצאה: 2 מול 2. למשתמש הסינתטי יש
שתי assignments, אחת exception ואחת לא; DISTINCT user משאיר אותו בשני הצדדים.
לא שינינו את ה־fixture או oracle אחרי ראיית הכשל.

זה אינו false positive מוכח של comparator: ה־rows אכן שקולים בנתונים שנבדקו.
זו מגבלת oracle/coverage: semantic score בודק הגדרות נדרשות, לא שלילה מלאה
של כל פילטר נוסף. ניגודים אחרים כן הובחנו (למשל W6C-004: 12 מול 23;
W6C-006 extra status: 5 מול 7; W6C-020 broad OR: 12 מול 5), אך אינם סוגרים
את הפער הכללי. ראיית provider לבדה גם לא תחליף fixture מבחין או inspection
של תוכנית מול הקריטריון; אין אישור לשנות scoring או thresholds במסגרת זו.

### F3 — מגבלת packing משוחזרת, אינה מכוונת למקרים שנחשפו

**Independently verified:** W6C-014 החדש דורש שמונה entities ושבע הגדרות
ביחסים מחוברים; כל המועמדים זמינים ב־15,819 bytes, והתוכנית נתנה oracle
נכון ולא־ריק (1 רשומה). הצלחת מקרה עומס אחד אינה הבטחת coverage כללית.

**Reproduced, known regression:** CA-B01 החשוף עדיין בגודל 15,969 bytes
ומחמיץ `open_support_ticket_older_than_30_days`,
`recent_privileged_group_membership`, `unused_license_assignment`.
79 מקרי W6a נשארו 69/69 חיוביים ו־5/10 controls מילוליים; חמש ציפיות empty
השתנו כבר ב־W6b ומפורטות בארטיפקט. אין ערבוב בינם לבין 20 מקרי ה־held-out.
P3 נשאר סיכון לא חוסם שהתקבל; לא שונו ranking, vocabulary, budget או bundles.

## שחזור ובדיקות

מה־root, ליצור container חדש (אם השם כבר קיים, לא למחזר/למחוק בלי לבדוק):

```sh
docker run --name queryops-w6c-offline -e POSTGRES_USER=queryops -e POSTGRES_PASSWORD=queryops -e POSTGRES_DB=queryops_w6c_test -p 127.0.0.1:55469:5432 -d postgres:16-alpine
cd backend
export DATABASE_URL=postgresql+psycopg://queryops:queryops@127.0.0.1:55469/queryops
export POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://queryops:queryops@127.0.0.1:55469/queryops_w6c_test
export POSTGRES_TEST_DATABASE_DISPOSABLE=1
PYTHONPATH=. .venv/bin/python ../docs/audits/w6c/probe.py --initialize --out /tmp/w6c-results.json
# להרצה חוזרת על אותו fixture: להשמיט --initialize.
PYTHONPATH=. .venv/bin/python ../docs/audits/w6c/selfcheck.py
```

ה־probe חוסם פלט לתיקיית הקורפוס; העתקת artifact שנבדק ל־Git נעשית בנפרד.
שלוש בדיקות tampering של [selfcheck.py](w6c/selfcheck.py) אישרו שינוי בשאלות,
בתוכניות או ב־fixture שנדחה לפני DB construction. הרצה ראשונה ואחריה replays
לא שינו ציפיות; נוספו בדיקות membership/runtime ושמונת join assignments כדי
לבאר את התוצאה. זמן/snapshot משתנים בין טרנזקציות; אין השוואת hash עיוורת שלהם.
הסקירה העצמאית זיהתה שבגרסה הראשונה של הכלי קובצי Python הקפואים יובאו
לפני hash validation. סדר הטעינה תוקן: hashes נבדקים לפני import של תוכניות/
fixture, ו־selfcheck בודק גם שה־imports לא הושגו בקלט שאינו תואם. אין כאן
הבטחת sandbox או הגנה מפני שינוי קבצים מקביל בידי גורם בעל הרשאות host.

מסד שני, port 55470 / `queryops_w6c_regression_test`, שימש לרגרסיות הקיימות
שמאפסות seed. הן לא שינו את fixture ה־held-out:

- **264 passed, 0 skipped:** candidate PostgreSQL/API, output identity PostgreSQL,
  evaluation runner PostgreSQL, relational semantics, query security,
  semantic plan/composition/conformance, scoring ו־semantic corrections.
- **292 passed:** provider, grounding, catalog, candidate, environment, evidence,
  provenance ו־dataset. אין לחבר totals כאומדן איכות מודל.
- Ruff של סקריפטי האימות, diff-check ו־source guard עברו.
  גרסאות dependencies המקומיות רשומות בארטיפקט; אין טענה לזהות עם גרסאות CI.
  ה־probe החדש הוא כלי audit שמורץ ידנית; בדיקות pytest הקיימות ב־CI אינן
  מוכיחות שהקורפוס החדש הורץ שם. הרצה עצמאית של הסוקר היא הראיה הנפרדת לכך.

## החלטה לפני live

[הצעת הניסוי התחומה](w6c/live-experiment-proposal.md) מגדירה בדיוק 12 שאלות
מהקורפוס, model label `gpt-5.6-terra`, reasoning low, output 2048, timeout 45s,
retries 0, עד 12 logical calls ועד 12 physical dispatches עם hard guard
שטרם מומש. יש לאשר בנפרד את כל הפרטים ואת זהות המקור/סביבה לפני ביצוע.
זמינות המודל בחשבון, usage, latency ו־provider accuracy לא נבדקו.

השלב הבא אינו tuning לפי התוצאות. יש להכריע בגבול המוצר של F1 ובתנאי
ההבחנה של F2; ניסוי חי מאושר יכול למדוד selection במקרים הנתמכים בלבד.
W7, שערי ה־release, canary×3/Full40 ו־manual QA נשארים דרישות נפרדות.

## סקירה עצמאית

סוקר בהקשר נקי קרא את המתודולוגיה וה־diff ושחזר את ה־probe על המסד המבודד
ללא initialization/reset. כל התצפיות היציבות תואמות ל־artifact, למעט זמן/
snapshot המשתנים מטבעם. בעיית סדר ה־imports בכלי תוקנה ונבדקה מחדש;
לא נשאר ממצא חוסם ל־PR ראיות לא ממוזג. פירוט וגבולות האישור נמצאים ב־
[independent-review.md](w6c/independent-review.md).
