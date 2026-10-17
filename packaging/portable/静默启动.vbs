' 程星 ONVIF 静默启动（不打开浏览器）
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = base & "\app"
sh.Run """" & base & "\python\pythonw.exe"" -m cxonvif serve --silent", 0, False
