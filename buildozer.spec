[app]
title = YT Bridge 4
package.name = ytbridge_v4
package.domain = org.redi2213
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf
source.exclude_dirs = tests,lab_examples
icon.filename = assets/icon.png
presplash.filename = assets/icon.png
android.presplash_color = #12203A
version = 2
requirements = python3,kivy,requests,certifi,plyer,arabic-reshaper,python-bidi==0.4.2,six,yt-dlp
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,POST_NOTIFICATIONS,REQUEST_INSTALL_PACKAGES,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,WAKE_LOCK,FOREGROUND_SERVICE,VIBRATE,READ_MEDIA_AUDIO,READ_MEDIA_VIDEO,READ_MEDIA_IMAGES,CAMERA,RECORD_AUDIO,MODIFY_AUDIO_SETTINGS,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION
android.api = 33
android.minapi = 21
android.archs = arm64-v8a
android.accept_sdk_license = True
android.sdk_path = /usr/local/lib/android/sdk

# Share target: lets other apps (YouTube, browsers, file managers) send a link
# to this app via the Android Share menu. See intent_filters.xml and
# core/android_share.py. singleTask makes an already-running app receive the
# new share instead of opening a second copy.
android.manifest.intent_filters = intent_filters.xml
android.manifest.launch_mode = singleTask

# The in-app browser's native half (java/org/redi2213/ytbridge/BrowserHelper.java): pyjnius cannot
# subclass WebViewClient, so a small Java class is compiled into the APK.
android.add_src = java

# Browser profiles: the WebView Profile API (separate cookies / storage per profile) is in androidx.webkit 1.9+.
android.enable_androidx = True
android.gradle_dependencies = androidx.webkit:webkit:1.9.0

[buildozer]
log_level = 2
warn_on_root = 1
