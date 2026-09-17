' Open Murmur -- pops the window (or signals a running instance to do so).
' Runs completely hidden via WScript.Shell so no console window appears.
' Resolves its own folder and its own Python, so the repo can live anywhere.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here

' Prefer a repo-local venv, then the official py launcher. A bare
' "pythonw" is the last resort because PATH often leads to an
' unrelated virtualenv before it reaches a real Python install.
venvPyw = here & "\.venv\Scripts\pythonw.exe"
sysPyw  = sh.ExpandEnvironmentStrings("%SystemRoot%") & "\pyw.exe"
If fso.FileExists(venvPyw) Then
  pyw = """" & venvPyw & """"
ElseIf fso.FileExists(sysPyw) Then
  pyw = """" & sysPyw & """"
Else
  pyw = "pythonw.exe"
End If

sh.Run pyw & " main.py --show", 0, False
