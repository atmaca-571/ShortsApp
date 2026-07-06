' kontrol_paneli_baslat.vbs
' Bu dosya, kontrol_paneli.pyw'yi HICBIR siyah pencere acmadan baslatir.
' Cift tikla, tek yapman gereken bu.

Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "pythonw.exe """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\kontrol_paneli.pyw""", 0, False
