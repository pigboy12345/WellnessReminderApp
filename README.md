# Wellness Reminder App

This project runs once per day, reads the current day’s reminders from Excel, schedules them by time, and records each outcome in SQL Server history.

It is designed for a Windows desktop environment and uses native Windows toast notifications, with a media popup fallback for GIFs and videos.

## Project structure

```text
WellnessReminderApp/
├── main.py                 # Application entry point
├── config.py               # Loads config.ini and .env values
├── config.ini              # Runtime settings for Excel, DB, notification, logging
├── .gitignore              # Ignores generated and sensitive files
├── requirements.txt        # Python dependencies
├── README.md               # Project documentation
├── schema.sql              # Reference SQL table definition
├── src/
│   ├── __init__.py
│   ├── db_service.py       # Writes reminder history to SQL Server
│   ├── excel_reader.py     # Reads and validates today’s reminder sheet
│   ├── logger_setup.py     # Logging configuration
│   ├── media_popup.py      # Custom popup for GIF/video reminders
│   ├── models.py           # Reminder data model
│   └── notification_service.py
├── data/
│   └── WellnessReminders.xlsx
├── assets/
│   └── logo.png
├── logs/
│   └── wellness_reminder.log
├── tests/
│   └── test_db_service.py
└── .env                    # Local DB credentials (not committed)
```

## How it works

1. The app reads the Excel file configured in [config.ini](config.ini).
2. It validates each row for required reminder fields.
3. It schedules reminders for the current date using APScheduler.
4. When a reminder fires, it shows a Windows toast or media popup.
5. Each action is logged to the SQL Server history table with machine/user metadata.
6. The process exits when all scheduled jobs and snoozes are finished.

## Excel reminder format

The Excel workbook should have a sheet named using the current date pattern, for example `02-09-2026`.

Required columns:
- id
- title
- message
- schedulingTime
- enabled

Optional columns:
- category
- icon/image

Example row:

```text
id | title | message | category | schedulingTime | enabled | icon/image
1  | Hydration | Drink water now | Wellness | 10:30 | TRUE | assets/sample.jpg
```

Notes:
- `schedulingTime` accepts `HH:MM` or `HH:MM:SS`.
- `enabled` accepts `TRUE`, `FALSE`, `1`, `0`, `yes`, or `no`.
- If `category` is missing, it defaults to `General`.
- If `icon/image` points to a GIF, video, or URL, the app opens a custom media popup instead of a normal toast.

## Database setup

This app writes to the table `GP_Custom.dbo.WellnessReminderHistory`.

The expected table structure is in [schema.sql](schema.sql). It stores:
- ReminderId
- Title
- Category
- TriggeredDateTime
- Status
- MachineName
- UserName
- ErrorMessage
- CreatedDateTime

Important:
- Install the SQL Server ODBC driver on the machine running this app.
- Put credentials in `.env`, not in source control.
- Example `.env`:

```env
DB_UID=your_user
DB_PWD=your_password
```

## Configuration

Edit [config.ini](config.ini) for:
- Excel file path
- SQL Server connection values
- reminder logo path
- snooze settings
- media popup behavior
- log file location

## Local run

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Packaging

You can package the app with PyInstaller if needed, but keep the runtime files together in the deployment folder:

```text
C:\Apps\WellnessReminder\
├── WellnessReminder.exe
├── config.ini
├── .env
├── data\WellnessReminders.xlsx
├── assets\logo.png
└── logs\
```

## Status values recorded

The app writes statuses such as:
- Triggered
- Completed
- Dismissed
- Snoozed
- Skipped
- Failed

## Notes

- Windows toast notifications require an interactive desktop session.
- The app is intended to run from Task Scheduler with the user logged in.
- Logs are written to [logs/wellness_reminder.log](logs/wellness_reminder.log).
