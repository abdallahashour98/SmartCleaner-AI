Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath

' Launch SmartCleaner.bat
WshShell.Run """" & strPath & "\SmartCleaner.bat""", 1, False
