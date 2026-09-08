Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath

' Launch SmartCleaner completely silently without console window (0 = Hidden)
WshShell.Run "cmd.exe /c """ & strPath & "\SmartCleaner.bat""", 0, False
