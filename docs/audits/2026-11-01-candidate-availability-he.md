# M10 W6b — Candidate Availability

## החלטה והיקף

זהו תיקון נפרד אחרי Output Identity, ששולב ב־PR #67 ב־
`722e6a092b53dd58b7f9779393273ed13cc70c33`. האישור מ־2026-11-01 מכסה זמינות
מועמדים בלבד. W6c, שינוי prompts/models, שיחות ספק בתשלום ו־release qualification
אינם מאושרים. המימוש המוצע טעון independent final review לפני merge.

נשמרה בחירת ה־context הקיימת, כולל סדרי העדיפויות ו־fail-closed על core גדול מדי.
אחריה `semantic_grounding._augment_available_context` מוסיף אפשרויות:

1. גרף מלא של entities ו־relationships שכבר עברו סינון authorization/schema,
   רק אם כולו נכנס בתקציב. אחרת נשאר הגרף המדורג הקיים, ללא הרחבה חלקית שרירותית.
2. הגדרות concepts, metrics ו־composition rules כתלויות סגורות ואטומיות. סדר
   הניסיון משתמש ב־`_description_score` הקיים, עם tie-break יציב לפי kind ו־ID.
   הציון קובע סדר בלבד: גם הגדרה ללא חפיפה מילולית רשאית להיכלל.
3. תוספת מתקבלת רק אם ה־JSON הסופי נשאר עד **16,000 bytes**. ההגדרות מסודרות
   לפי ID כדי לשמר canonical observations. לא משנים או מפנים core כדי לפנות מקום.

אין תוספת `candidate_signals`, lexical evidence, authoritative terms, examples,
RequiredIntent או SuggestedIntent. הגדרה זמינה אינה הוראה לבחור אותה; רק plan
שנבחר ונבדק קובע predicates. אין parser נוסף, embeddings, קריאת ספק נוספת, שינוי
אלגברה, schema, migration או dependency חדשה. הבעלות על SQL נשארה דטרמיניסטית.

## השוואת חלופות

| חלופה אופליין | positive cases עם מלוא ה־context הצפוי | מחיר / סיבת דחייה |
| --- | ---: | --- |
| baseline ב־main | 40/69 | lexical gating משאיר משפחות לגיטימיות ללא אפשרויות |
| vocabulary צר בבעלות catalog | 53/69 | דוגמה אפשרית בלבד; עדיין תלויה בניסוח ואינה פותרת זמינות הגדרות מורכבות |
| כל הגרף המורשה, הגדרות קיימות בלבד | 60/69 | פתרון קטן אך חסרות הגדרות עסקיות |
| כל facts והגדרות ללא סלקציה | 69/69 לפני תקציב; 0/69 בתוך התקציב | 18,366 bytes; נדחה, ללא הגדלת cap או דחיסה חדשה |
| גרף מורשה + bundles תקציביים, המימוש הנבחר | 69/69 | שומר core; שפע אפשרויות עשוי להשפיע על בחירת ספק שטרם נמדדה |

ה־vocabulary החלופי נבנה ידנית להשוואת מנגנונים, ולא מוכיח שהמילים שנבחרו הן
הטקסונומיה הנכונה. לא שונה catalog. אין טענה שזהו האלגוריתם האופטימלי או שהקשר
נוסף משפר תשובות; היתרון שנמדד הוא ביטול omissions ללא שינוי גבולות אבטחה.

## baseline שחזור ותוצאות

המקור, catalog, frozen corpus, dataset digest וגרסאות Python/runtime רשומים ב־
[artifact](2026-11-01-candidate-availability-results.json). ה־source hashes מתארים את
הקבצים שנבדקו גם כאשר `current_head` הוא commit האב של שינויים שטרם בוצע להם commit.
מקור baseline הוא `722e6a0`; קוד grounding זהה ל־W6a `b1f03a4`.
ה־probe משחזר את כל 79 רשומות baseline מול IDs וגדלי JSON הקפואים, ולא רק ציון כולל.

| רכיב צפוי במקרים החיוביים | לפני | אחרי |
| --- | ---: | ---: |
| Entities | 56/91 | 91/91 |
| Relationships | 7/13 | 13/13 |
| Concepts | 30/40 | 40/40 |
| Composition rules | 3/6 | 6/6 |
| Metrics | 3/3 | 3/3 |
| מקרים עם מלוא הרכיבים הצפויים | 40/69 | 69/69 |

אין regression חיובי בקורפוס; כל 22 המקרים הקנוניים שהצליחו נשמרו. הגדלים אחרי
התיקון: 362–16,000 bytes. נבדקו authorization eligibility, dependency closure,
דטרמיניזם, שימור כל רשומות ה־core ושימור metadata של הכוונה וה־lexical evidence.

**ה־controls הישנים אינם מוצגים ככולם עוברים:** 10/10 לפני ו־5/10 אחרי בהשוואה
מילולית. חמש ציפיות `empty entities` השתנו: ambiguous, value-only, no-assigned-scope,
non-queryable target ו־restricted target. המימוש מציע משאבים אחרים שמורשים גם כשאין
התאמה מילולית או כשהיעד אינו זמין. לדוגמה, בלי scope עדיין ניתן להציע reference
resource גלובלי שמותר לפי schema. היעד האסור ותלויות אסורות נשארים בחוץ. לא שונו
הקורפוס או ציפיותיו כדי להסתיר זאת; ה־artifact מפרט כל שינוי. negated metric אינו
הופך ל־lexical match, ו־service-account decoys אינם הופכים לפילטר מחייב.

זהו **known regression corpus**, לא held-out ולא ראיה ל־provider selection,
פירוש עסקי, דיוק SQL או answer quality. אין להסיק מכך פתרון ל־medium-009 או V1 readiness.

## בדיקות ושחזור

- לפני התיקון: `tests/test_candidate_availability.py` הראשוני נתן 4 failed,
  3 passed; לאחריו כל אותם 7 עברו. נוספו שלוש בדיקות ל־shallow checkout,
  דטרמיניזם בסידור catalog שונה ו־atomic bundle תחת תקציב.
- `tests/test_candidate_availability_postgres.py`: **14 passed, 0 skipped** מול
  PostgreSQL 16.14 מבודד. נבדקו permissions/scopes נוכחיים, revocation, resource
  exposure/queryability, API, RLS, negative/ambiguous/negated plans ו־safe outbound
  projection ללא identities, scope keys או rows. הספק הוא seam מבוקר, לא LLM חי.
  restricted columns נבדקו דרך DomainPack/schema seam; אין כאן טענת field ACL חדש.
- הריצה הרחבה הראשונה עם PostgreSQL נתנה 1,960 passed ו־1 failed: סיכום Mock
  ירד מ־11 ל־10. השוואת baseline/current זיהתה רק `itops-security-003`, שנחסם
  נכון בשניהם, אך Mock דיווח את כל ה־candidate tables כ־referenced tables.
  תוקן adapter ה־Mock כך שידווח רק על lexical entity evidence; נוסף regression
  שנכשל לפני התיקון. לא השתנו expected answers, scoring או thresholds. זהו דיווח
  Mock על התאמה מילולית, לא ראיה ל־SQL שבוצע; unsafe request אינו מייצר plan.
- בדיקות קיימות שציפו ל־context בלעדי/ריק עודכנו לבדוק את ההבחנה החדשה:
  זמינות מורשית לעומת lexical/required meaning. איסורי הרשאות, closure, safety
  caps ו־semantic conformance לא הוחלשו.
- CI קיים אוסף את קובצי הבדיקה דרך full pytest. בדיקת הקורפוס אינה דורשת Git
  history ולכן עובדת גם ב־shallow checkout. ה־probe ההשוואתי המקומי כן דורש את
  commit ה־baseline, ומאמת frozen hashes לפני ההשוואה.

```sh
cd backend
PYTHONPATH=. .venv/bin/python scripts/probe_candidate_availability.py
.venv/bin/pytest tests/test_candidate_availability.py -q
# רק עם POSTGRES_TEST_DATABASE_URL מבודד ו־POSTGRES_TEST_DATABASE_DISPOSABLE=1:
.venv/bin/pytest tests/test_candidate_availability_postgres.py -q -rs
```

הבדיקות המלאות, CI וה־PR בפועל מתועדים ב־
[development history](../history/development-history.md). ניסיון initial full-suite
נחסם ב־sandbox TCP והופסק; הוא אינו pass או כשל מוצר. הריצה התקפה משתמשת בגישה
מאושרת ל־PostgreSQL זמני בלבד. לא נעשה שימוש ב־DB רגיל או בספק בתשלום.

## מגבלות והמשך

catalog גדול יותר עלול לא להכניס את כל הגרף; אז נשמר ranked core וקיימת עדיין
מגבלת recall מתועדת. גם עם גרף זמין, חלק מההגדרות עלולות לא להיכנס; אין הבטחת
כל־catalog. אין metrics על false provider selections או latency של ספק. הסרת
lexical gating מגדילה אפשרויות ועשויה להקשות על interpretation; אין הסתרה של סיכון זה.

Independent final review צריך לבנות ולשמור מקרים בלתי נראים בנפרד ולבדוק במיוחד
הרשאות, ambiguity, decoys, atomic budgets והיעדר משמעות מחייבת. הוא אינו בוצע בידי
מחברי התיקון ואינו מוחלף בבדיקת helper של מחבר הבדיקות. אין להתחיל W6c או tuning.
