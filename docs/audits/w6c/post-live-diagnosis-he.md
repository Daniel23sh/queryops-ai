# W6c v2 — אבחון לאחר ריצת Live הראשונה

זהו אבחון offline של ראיות קיימות ושינוי תצפיתיות בלבד. לא בוצעו קריאת
OpenAI חדשה, replay, resume, תיקון prompt/model/catalog או שינוי סמנטיקת מוצר.
ה־[חוזה המאושר](live-experiment-v2.md), השאלות, ה־oracles, ה־hashes וה־fixtures
המקוריים נשארו ללא שינוי. סמנטיקת production Evaluation לא השתנתה.

## מקור הראיות והגבולות

היומן הבטוח המקומי והסיכום המקומי היו זמינים בעת האבחון. היומן נקרא בלבד;
SHA256 שלו לפני העבודה ואחריה חייב להישאר:
`f750227e1f186fced226ddee4e84e6b4687a0d47daa8e75179c2950b45dcaef8`.
הסיכום הוא ראיה נגזרת, לא מקור עצמאי לתוכן provider שאינו ביומן. אין העתק
של היומן, אישור המפעיל, provider payload, SQL, rows או סודות ב־PR זה.

זהות הניסוי המקורי:

- Source: `23b6980d43ec980cf60fa9707815d4fc01a568f9`.
- Fingerprint: `313562cd4451655c6d106edad16ed5247ec45da6700aebdec717429bbda371e5`.
- Reference: `2026-11-03T14:14:48Z`.
- מודל מאושר: `gpt-6.1-terra`, low/2048/45/0; PostgreSQL 16.15,
  Python 3.13.11, SDK 2.46.0.

## ממצאים מאומתים

נרשמו 8 logical calls, 8 dispatch reservations/results, 7 case results ואירוע
sequence_failed אחד. לכל שאלה נרשם dispatch אחד בלבד. ארבע השאלות האחרונות
לא נשלחו. הסדר וה־fingerprint ביומן תואמים לניסוי המאושר.

| מקרה | מה הראיות הקיימות מוכיחות |
| --- | --- |
| W6C-001 | plan; combined oracle_equal=true, השוואה מלאה באותו snapshot לקריאה בלבד |
| W6C-002 | clarification, semantic_match=true |
| W6C-003 | clarification, semantic_match=true |
| W6C-004 | plan; combined oracle_equal=true |
| W6C-006 | plan; combined oracle_equal=true |
| W6C-008 | plan; oracle_complete=true, same_read_only_snapshot=true, combined oracle_equal=false |
| W6C-009 | plan; combined oracle_equal=true |
| W6C-007 | transport_or_interruption, זמן 45,003.455ms, usage_complete=false, ללא case result |
| W6C-011/012/013/020 | אין logical-call או dispatch event; לא נבדקו Live |

במקור הניסוי, oracle_equal היה `output_ok AND rows_equal`. כאשר output_ok
היה false, ההשוואה השנייה כלל לא הוערכה בגלל short circuit. לכן **אי אפשר
לשחזר איזה תנאי נכשל ב־W6C-008**, האם התוצאות היו שונות או האם לא הושוו.
ה־plan, הפלט הגולמי וסיבות השוואה נפרדות לא נשמרו. passing conformance
מעיד על התאמת ה־SQL לתוכנית שהתקבלה, לא על התאמת אותה תוכנית לשאלה.

ב־W6C-007 קוד המקור כיווץ את כל החריגות שאינן DiagnosticStop לקטגוריה
transport_or_interruption. אין ראיה שמאפשרת להפריד בדיעבד timeout, connection,
protocol או interruption. אין תוצאת provider או plan שמאפשרים לבדוק בחירת
left_reverse. התמיכה הדטרמיניסטית ושימור ענפי OR נשארים ראיות offline.

## השערות סבירות וראיות חסרות

- משך W6C-007 קרוב מאוד ל־timeout המוגדר של 45s, ולכן timeout הוא הסבר
  סביר, **לא סוג חריגה מאומת**. אין להסיק מכך שהמודל התקשה באלגברה או שמודל
  אחר/timeout אחר היה מצליח.
- W6C-008 עשוי להיות פער בחוזה פלט, פער ב־multiset או שניהם. אין בסיס
  לייחס זאת ל־DISTINCT, filter מסוים, fanout או תוכנית מסוימת.
- אין נתוני provider מקוריים נוספים, traceback בטוח או חיוב מאומת שניתן
  לשחזר באמצעות בדיקה מקומית. היעדרם אינו הרשאה לשחזור/ניסוי נוסף.

## שימוש ועלויות

בשבע התשובות עם usage מלא: 50,756 input, מהם 12,726 cached-input,
715 output, סך 51,471 tokens. input כולל cached-input; אין לחבר אותם שוב.
זמן dispatch מצטבר: 29.714949s לתשובות שהושלמו, 45.003455s לניסיון שלא
הושלם, יחד 74.718404s. אלה אינם זמני wall-clock מלאים של הניסוי.

כל מוני השימוש ב־W6C-007 הם null, לא 0. לכן שימוש/חיוב כולל לניסוי אינו
ידוע; אין להסיק שהקריאה שנכשלה הייתה חינם. האומדן החלקי בסיכום המקורי
אינו חשבונית ואינו משחזר את עלות הניסיון השמיני.

## שינוי התצפיתיות ומסקנה

התצפיתיות [מפרידה מעתה](../../development/w6c-observability.md) בין התאמת חוזה
פלט לבין multiset תחת זהויות תואמות, ושומרת קטגוריות transport לפי החריגה
האמיתית בגבול ה־HTTP. שדות legacy נשמרים ואינם מקבלים בדיעבד משמעות חדשה.
הבדיקות משתמשות רק בתוכניות סינתטיות, fake HTTP ו־PostgreSQL חד־פעמי נפרד.
אף mutation בבדיקה אינו שחזור של התוכנית המקורית או הסבר לממצא ההיסטורי.

יש הצדקה מקצועית לשקול בעתיד מדידה ממוקדת שתפיק את הראיות החסרות, אבל
**אין לכך אישור במסגרת עבודה זו**. תחילה יש לסיים סקירה/CI של התצפיתיות,
ואז להגדיר היקף ניסוי וזהויות חדשים ולקבל אישור מפעיל נפרד לכל מודל,
settings, שאלות, fingerprint ותקציב. אין לאפס/למחוק/להחליף את יומן v2 או
להשתמש ביתרת התקציב שלו. לא נוצרה כאן גרסת ניסוי חדשה או דרך עוקפת.

זה אינו V2 canary/full40 או ראיית V1 release readiness.
