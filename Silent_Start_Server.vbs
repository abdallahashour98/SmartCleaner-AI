Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

' Kill lingering old ngrok and server processes first
WshShell.Run "cmd.exe /c taskkill /F /IM ngrok.exe", 0, True

' Start server silently in the background
WshShell.Run "cmd.exe /c Run_Server.bat", 0, False
