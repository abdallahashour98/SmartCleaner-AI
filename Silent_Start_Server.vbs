Set WshShell = CreateObject("WScript.Shell")

' Kill lingering old ngrok and server processes first
WshShell.Run "cmd.exe /c taskkill /F /IM ngrok.exe", 0, True

' Start SmartCleaner-AI Server & dynamic Ngrok tunnel silently in the background (0 = hidden)
WshShell.Run "cmd.exe /c py -3.10 server_api.py --with-ngrok", 0, False
