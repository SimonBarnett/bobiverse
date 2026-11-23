# TipForm Exit leaves ircBob running (FR #9034)

TipForm Exit must not run `sc stop ircBob`. Ear recycle is Restart-BobEar.
PS TipForm omits -StopService; bob-tray.exe ExitTray no longer Detached-stops ircBob.
