Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath

' Check if portable runtime exists, otherwise fallback to system pyw
If fso.FileExists(strPath & "\runtime\pythonw.exe") Then
    WshShell.Run """" & strPath & "\runtime\pythonw.exe"" """ & strPath & "\gui_cleaner.py""", 0, False
Else
    WshShell.Run "pyw -3.10 """ & strPath & "\gui_cleaner.py""", 0, False
End If
