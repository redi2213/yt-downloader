[app]
title = YT Downloader
package.name = ytdownloader
package.domain = org.redi2213
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy,requests,certifi
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.archs = arm64-v8a
android.accept_sdk_license = True
android.sdk_path = /usr/local/lib/android/sdk

[buildozer]
log_level = 2
warn_on_root = 1

