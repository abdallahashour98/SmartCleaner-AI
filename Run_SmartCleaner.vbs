Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath

' Launch Python GUI with pyw (no console window) in completely hidden mode (0)
WshShell.Run "pyw -3.10 """ & strPath & "\gui_cleaner.py""", 0, False
