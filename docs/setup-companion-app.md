# Phone setup (Home Assistant Companion app)

Sunrise Alarm can read the next alarm you set in your normal phone clock app.

1. Install the **Home Assistant Companion** app and sign in to your HA.
2. App configuration → **Manage sensors** → enable **Next alarm**. Confirm
   `sensor.<device>_next_alarm` appears in HA after you set a phone alarm.
3. When adding a Sunrise Alarm profile, choose that sensor as the
   *Phone "Next alarm" sensor*.

Notes:
- The Next-alarm sensor exposes a `Package` attribute naming the app that set the
  alarm. Sunrise Alarm only accepts alarms from the Google Clock
  (`com.google.android.deskclock`) or Samsung Clock
  (`com.sec.android.app.clockpackage`) by default — this is what filters out
  calendar reminders and Routines. You can change the allowed packages later if
  your device differs.
- Set an **internal URL** (Settings → System → Network) so the Companion app can
  reliably push the sensor. A stale registration can stop the alarm time updating
  overnight; treat a fresh `next_alarm` timestamp as the health check.
- No phone sensor? Leave it blank and drive the profile with the `start` service
  from your own automation or a fixed-time trigger instead.
