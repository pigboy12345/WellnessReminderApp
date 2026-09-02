-- Reference schema. Create only if the table does not already exist.
IF OBJECT_ID('GP_Custom.dbo.WellnessReminderHistory', 'U') IS NULL
BEGIN
    CREATE TABLE WellnessReminderHistory (
   [SI No] INT IDENTITY(1,1) PRIMARY KEY,
   ReminderId VARCHAR(50) NOT NULL,
   Title VARCHAR(200) NOT NULL,
   Category VARCHAR(100) NOT NULL,
   TriggeredDateTime DATETIME NOT NULL,
   [Status] VARCHAR(20) NOT NULL
       CHECK ([Status] IN ('Triggered', 'Completed', 'Skipped', 'Failed', 'Snoozed', 'Dismissed')),
   MachineName VARCHAR(100) NOT NULL,
   UserName VARCHAR(100) NOT NULL,
   ErrorMessage VARCHAR(500) NULL,
   CreatedDateTime DATETIME DEFAULT GETDATE()
);
CREATE INDEX idx_TriggeredDateTime
   ON WellnessReminderHistory(TriggeredDateTime DESC);
CREATE INDEX idx_ReminderId
   ON WellnessReminderHistory(ReminderId);
END
