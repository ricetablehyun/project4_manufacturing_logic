import sys, zipfile, re
src, dst = sys.argv[1], sys.argv[2]
T = '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"><mc:Choice xmlns:p159="http://schemas.microsoft.com/office/powerpoint/2015/09/main" Requires="p159"><p:transition spd="slow" xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main" p14:dur="1500"><p159:morph option="byObject"/></p:transition></mc:Choice><mc:Fallback><p:transition spd="slow"><p:fade/></p:transition></mc:Fallback></mc:AlternateContent>'
zi = zipfile.ZipFile(src); zo = zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED)
n = 0
for it in zi.infolist():
    d = zi.read(it.filename)
    if re.match(r'ppt/slides/slide\d+\.xml$', it.filename):
        s = d.decode('utf8')
        s = re.sub(r'<p:transition.*?</p:transition>|<p:transition[^>]*/>', '', s)
        assert '</p:clrMapOvr>' in s, it.filename
        s = s.replace('</p:clrMapOvr>', '</p:clrMapOvr>' + T, 1); n += 1
        d = s.encode('utf8')
    zo.writestr(it, d)
zo.close(); print('morph on', n, 'slides')
