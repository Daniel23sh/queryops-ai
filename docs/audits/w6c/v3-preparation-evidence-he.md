# W6c v3 — ראיות הכנה אופליין

ההרשאה מ־2026-11-04 מוגבלת להכנה ומימוש. [החוזה](live-experiment-v3.md)
מקבע שישה מקרים, config, בידוד יומן ודרישת אישור עתידי נפרד.
[Draft PR #75](https://github.com/Daniel23sh/queryops-ai/pull/75) נפתח נגד `main`;
אין כאן אישור מפעיל, ריצת ספק, qualification חדש או החלטת merge.

## מקור ו־preflight

העבודה התחילה מ־`main` נקי ומעודכן:
`2c0c4459caf9840beff421664eff2922ab8dc604`, בענף
`feature/m10-w6c-v3-preparation`. המימוש והבדיקות נבדקו במקור נקי:
`f46f58a89f9b6b3c45643ecf1e2936ffa75f90fd` (לאחר תיקון ACL בסקירה). עדכוני תיעוד מאוחרים יותר
אינם הופכים את הזהות הזו לזהות מפעיל מאושרת.

ה־CLI האמיתי ביצע `--initialize` מול אשכול PostgreSQL חדש בבעלות ההרצה,
עם מסד ריק בשם `queryops_w6c_v3_test`, migrations ו־small seed + frozen
contrasts מעוגנים לזמן חדש. האשכול הוסר בניקוי בבעלות ההרצה בלבד; לא אומצו
או אופסו מסדי נתונים/containers/roles קיימים. טבלאות הייחוס הגלובליות נשארו
לפי חוזה ה־scope הקיים; מדיניות RLS והרשאות המוצר לא שונו.

| זהות הכנה | ערך |
| --- | --- |
| UTC reference | `2026-11-03T23:00:12+00:00` (2026-11-04 לפי זמן המפעיל) |
| Offline fingerprint | `db95e0d6f14329f96d04a865f3bbd2ee68d5420e3358a39c815d5f13515b9076` |
| Database fingerprint | `e89d8a15f862ed7dae7a296c50d98e8ea028caaf16886af8b809fd029ea98277` |
| Runtime policy hash | `6aefe849be921ac276f93ba8c20c385e6b5ef3f5f888627d87b72fcbb948392c` |
| v3 configuration hash | `c8d478bda873018d7bdcc53a25a16b032d8f9c09b7a8581bbec37db1a6865df1` |
| Provider runtime digest | `032168fecf1973ef470e85a5a828f1a27c367e9ba12cf8a58adbb11f563ceb04` |
| Migration | `0010_disable_inactive_user` |
| PostgreSQL / Python | `16.15` / `3.13.11` |

כל ששת ה־witnesses העצמאיים עברו מול ה־oracles המקוריים. בכל מקרה, זוג
ה־witness וה־oracle הושוו באותו snapshot לקריאה בלבד תחת
`queryops_query_runtime`; לששת המקרים transactions נפרדים. output contract ו־result multiset
התאימו ב־6/6, כולל שימור שני ענפי OR וה־WHERE העצמאי ב־W6C-007.
ה־preflight רשם 0 logical/physical calls. הרצה חוזרת לקריאה בלבד מאותו
reference שחזרה את כל ה־manifest בדיוק.

גרסאות runtime בפועל, ללא החלפת SDK או שינוי settings לצורך מעבר:

| חבילה | גרסה |
| --- | --- |
| openai | 2.46.0 |
| httpx / httpcore | 0.28.1 / 1.0.9 |
| pydantic / pydantic-core | 2.13.4 / 2.46.4 |
| psycopg / psycopg-binary | 3.3.4 / 3.3.4 |
| sqlalchemy / alembic | 2.0.51 / 1.18.5 |
| sqlglot | 30.17.0 |
| anyio / jiter | 4.14.1 / 0.16.0 |
| fastapi / starlette | 0.115.14 / 0.46.2 |
| faker / typing-extensions | 39.1.0 / 4.15.0 |

## הוכחת אופליין ובידוד יומנים

ה־CLI של dry-run קרא את ה־manifest ושלח בדיוק שש בקשות דרך parser ה־SDK
האמיתי ו־MockTransport. כל שש התוצאות תאמו ל־oracles. יצירת HTTPTransport
אמיתי נחסמה בבדיקה, ו־Python audit hook אסר כל `socket.connect`; חיבור
PostgreSQL המקומי ב־libpq נותר זמין למסד הייעודי בלבד. סביבת התהליך הייתה
מינימלית וסינתטית, ללא מפתח ספק. **מספר בקשות ספק אמיתיות: 0**. בדיקות
PostgreSQL הממוקדות ושערי המימוש רצו גם ב־network namespaces מבודדים.

לפני ואחרי ה־CLI נבדק לקריאה בלבד SHA256 של יומן v2:
`f750227e1f186fced226ddee4e84e6b4687a0d47daa8e75179c2950b45dcaef8`.
הוא תאם לזהות ההיסטורית. תיקיית היומן האמיתית של v3 לא הייתה קיימת לפני
ההרצה וגם אחריה. לא נוצר קובץ אישור מפעיל אמיתי. ה־manifest, תוצאות ה־dry-run
והיומנים הסינתטיים לא צורפו למאגר; התיעוד מכיל סיכום בטוח בלבד.

## בדיקות וסקירה

- 136 בדיקות unit של v2/v3/dispatch עברו בסקירה העצמאית לאחר השלמת כיסוי
  היומן. בדיקות v2 ההיסטוריות נשארו ללא שינוי.
- ההרצה הממוקדת הראשונית מול PostgreSQL חדש סיימה 176 בדיקות ללא כשל או
  דילוג. לאחריה נוספו בדיקות בעלות/נתיב יומן וניסיון הפעלה שני לאחר כשל.
- הכיסוי כולל תקציב, כפילות/תחרות, reservation לפני dispatch, כתיבה/fsync
  שנכשלו, הפסקה, journal reuse, זהות/authorization drift, schema/model/usage
  שגויים, malformed/refusal, approval mismatches ובידוד בין גרסאות.
- semantic mismatches בטוחים ממשיכים עם contract/result נפרדים; שינוי
  משמעות שאינו בר השוואה נשמר `not_evaluated`. fatal failures מפסיקים לפני
  המקרה הבא, ושומרים stage בטוח ומונים ללא raw exception/provider/SQL/rows.
- סקירת V3 עצמאית בהקשר חדש בדקה version isolation, dispatch/usage accounting,
  בעלות ועמידות היומן, approval gates ושימור v2. בשלב הראשון לא נמצאו תקלות חוסמות.
  פער הבדיקות הראשוני בבעלות/הרשאות/symlinks/fsync של נתיב היומן נסגר ונבדק
  מחדש. הסוקר לא הפעיל ספק ולא שינה יומן אמיתי.

בבדיקת גבול נוספת אושר פער ב־fingerprint: ACL ברמת עמודה ו־public schema
לא נכלל בזהות המשותפת של v2. v3 בלבד הורחב לכלול column grants ו־schema
owner/ACL; v2 לא שונה. נוספו בדיקות drift ב־PostgreSQL לשני המצבים. לאחר
התיקון עברו **187 בדיקות ממוקדות, ללא כשל או דילוג**, באשכול חדש עם network
namespace מבודד. זהו פער באכיפת זהות אבחונית, לא ראיה לעקיפת הרשאות במוצר.
הסוקר בדק מחדש את התיקון ואת שלושת קובצי הראיות הבטוחים: manifest,
dry-run ו־journal-isolation. הוא חישב מחדש את ה־fingerprint, אימת את כל
הזהויות/הגרסאות/ששת המקרים/המונים ואת בידוד היומנים. לא נותרה אי־התאמה.
אין הסתמכות על דיווח המחבר בלבד; המסד שכבר נוקה לא הורץ מחדש בידי הסוקר.

כל ששת שערי [CI הראשוני](https://github.com/Daniel23sh/queryops-ai/actions/runs/41734486970)
עברו על `0a1b09f`. ה־preflight המתוקן וה־dry-run של `f46f58a` עברו ונבדקו
עצמאית, כמפורט לעיל. Handoff מותנה בהצלחה של כל ששת השערים גם ב־HEAD הסופי
של [Draft PR #75](https://github.com/Daniel23sh/queryops-ai/pull/75); זהות ה־commit
והריצה הסופיים נשמרים ב־checks של ה־PR ובדוח המסירה.

## עלות משוערת ואי־ודאות

לפי [תיעוד המודל הרשמי](https://developers.openai.com/api/docs/models/gpt-6.1-terra)
ו־[מחירון API](https://developers.openai.com/api/docs/pricing) שנבדקו בזמן
ההכנה, Standard הוא $1 למיליון input tokens ו־$5 למיליון output;
cached input הוא $0.05 למיליון. אין כאן בדיקת זמינות או חשבון ספק.

שבע התשובות ההיסטוריות עם usage מלא צרכו 50,756 input ו־715 output.
אקסטרפולציה לשש קריאות נותנת כ־43,505 input וכ־613 output: כ־**$0.047**
בהנחת input שאינו cached. באותו נפח input ובמלוא allowance של
`6 × 2048 = 12,288` output tokens: כ־**$0.105**. עבור 40–60 אלף input
והגעה למלוא output cap האומדן הוא כ־**$0.10–$0.12**, ללא מס/עמלות.

זה אומדן בלבד, לא תקרת חיוב: ששת המקרים שונים, tokenizer ושימוש בפועל לא
נמדדו, reasoning ושימוש בניסיון שנכשל עשויים להשפיע, cache/cache-write ותעריף
החשבון יכולים לשנות מחיר. synthetic dry usage אינו בסיס לחישוב עלות. מוני
usage חסרים נשארים לא ידועים, וכשל אינו נחשב חינם. יש לעדכן מחיר והנחות
בבקשת ההרשאה הנפרדת; input כולל cached input ואין לחבר אותו פעמיים.

## תנאי handoff וסיכונים שנותרו

זהו ניסוי ממוקד וחשוף אחרי אבחון, לא held-out generalization או V1/V2
qualification. לא נמדדו פרשנות ספק, איכות NL או זמינות המודל. תלויות בטווחי
גרסאות אינן lock מלא; manifest מזהה את מה שנבדק בפועל. גבול היומן סומך על
המפעיל המקומי ואינו מונע ממנהל OS למחוק מצב או להפעיל לקוח HTTP אחר.

יש לעצור ב־Draft PR הנסקר. אחרי merge עתידי שאושר בנפרד: fetch, מקור נקי
HEAD = main = origin/main, אשכול/מסד v3 ריקים חדשים, reference חדש,
preflight/dry-run חדשים, וסקירת SHA/fingerprint/גרסאות/fixture/מדיניות/שאלות/
settings/עלות/תנאי עצירה. רק לאחר מכן מבקשים אישור אנושי מפורש ל־6/6/1
בדיוק, ויוצרים קובץ v3 נפרד לפי [חוזה האישור](live-experiment-v3.md).
**ה־fingerprint המוצג כאן אינו מאושר להפעלה.**
