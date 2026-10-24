"""Android notifications that open the app on a given job when they are tapped.

plyer's notification cannot carry data, so this builds the notification with pyjnius: the tap
launches the app (it is singleTask, so a running app gets onNewIntent) with the job id and run id
as extras; core/android_share.py hands them to the navigator, which opens that job's result.

Everything is wrapped: on desktop (no jnius) or if anything fails, show() returns False and
services/notify_service.py falls back to plyer.
"""
EXTRA_JOB = "yt_job_id"
EXTRA_RUN = "yt_run_id"
CHANNEL_ID = "yt_bridge_jobs"


def request_permission():
    """Android 13+: asks for the notification permission (the manifest alone is not enough)."""
    try:
        from jnius import autoclass
        if autoclass("android.os.Build$VERSION").SDK_INT < 33:
            return
        from android.permissions import request_permissions
        request_permissions(["android.permission.POST_NOTIFICATIONS"])
    except Exception:
        pass


def show(title, message, job_id=None, run_id=None):
    """Shows the notification. True if Android showed it, False if the caller should fall back."""
    try:
        from jnius import autoclass
    except Exception:
        return False
    try:
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        if activity is None:
            return False
        Context = autoclass("android.content.Context")
        Intent = autoclass("android.content.Intent")
        PendingIntent = autoclass("android.app.PendingIntent")
        Builder = autoclass("android.app.Notification$Builder")
        sdk = autoclass("android.os.Build$VERSION").SDK_INT
        manager = activity.getSystemService(Context.NOTIFICATION_SERVICE)
        if sdk >= 26:
            Channel = autoclass("android.app.NotificationChannel")
            manager.createNotificationChannel(Channel(CHANNEL_ID, "YT Bridge jobs", 3))
            builder = Builder(activity, CHANNEL_ID)
        else:
            builder = Builder(activity)
        intent = activity.getPackageManager().getLaunchIntentForPackage(activity.getPackageName())
        if intent is None:
            return False
        intent.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP)
        intent.putExtra(EXTRA_JOB, str(job_id or ""))
        intent.putExtra(EXTRA_RUN, str(run_id or ""))
        key = str(job_id or run_id or (str(title) + str(message)))
        notif_id = sum(ord(c) * (i + 1) for i, c in enumerate(key)) % 2147483000
        flags = PendingIntent.FLAG_UPDATE_CURRENT
        if sdk >= 23:
            flags |= PendingIntent.FLAG_IMMUTABLE
        pending = PendingIntent.getActivity(activity, notif_id, intent, flags)
        builder.setSmallIcon(activity.getApplicationInfo().icon)
        builder.setContentTitle(str(title))
        builder.setContentText(str(message))
        builder.setContentIntent(pending)
        builder.setAutoCancel(True)
        manager.notify(notif_id, builder.build())
        return True
    except Exception:
        return False


def ids_from_intent(intent):
    """(job_id, run_id) carried by a notification's intent, or None."""
    if intent is None:
        return None
    try:
        job = intent.getStringExtra(EXTRA_JOB)
        run = intent.getStringExtra(EXTRA_RUN)
    except Exception:
        return None
    job = str(job) if job else ""
    run = str(run) if run else ""
    return (job, run) if (job or run) else None
