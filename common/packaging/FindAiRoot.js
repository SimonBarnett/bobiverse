// FindAiRoot.js - MSI immediate custom action (JScript, t780u). Sets the AIROOT property = the "<drive>:\ai" folder the
// bobiverse products live in. Same rules as Get-BobiverseAiRoot (Bobiverse-Common.ps1) and ai_root.py:
//   1. env BOB_AI_ROOT (or a command-line AIROOT=... , handled by the CA condition)
//   2. FIXED disks only (Scripting.FileSystemObject DriveType 2 = fixed; removable/network/CD are ignored) that have \ai
//   3. several -> the one already holding bob\jeeves\airc\ergo, then the one the fleet services (ircBob/ircJeeves/BobIrcd/Airc)
//      point at, then the system drive, then drive-letter order
//   4. none -> <SystemDrive>\ai (MSI creates it as the parent of INSTALLDIR; nothing is created here)
// Keep this file free of any hard-coded drive-letter ai path. Pack-BobiverseRelease.ps1 embeds it in the MSI Binary table.
function bobAiLetter(p) {
    var m = /^\s*"?([A-Za-z]):/.exec(String(p));
    return m ? m[1].toUpperCase() : '';
}
function bobPickAiRoot(o) {
    // o = { override, systemDrive:'C:', drives:[{letter:'D', type:2, hasAi:true, installs:2}], svcLetters:['C'] }
    if (o.override) { return String(o.override).replace(/[\\\/]+$/, ''); }
    var sys = String(o.systemDrive || 'C:').replace(/[\\\/]+$/, '').toUpperCase();
    var c = [], i, j;
    for (i = 0; i < o.drives.length; i++) {
        var d = o.drives[i];
        if (d.type === 2 && d.hasAi) {
            var svc = 0;
            for (j = 0; j < o.svcLetters.length; j++) { if (o.svcLetters[j] === String(d.letter).toUpperCase()) { svc++; } }
            c.push({ letter: String(d.letter).toUpperCase(), inst: d.installs || 0, svc: svc, sys: (String(d.letter).toUpperCase() + ':' === sys) ? 1 : 0 });
        }
    }
    if (c.length === 0) { return sys + '\\ai'; }
    c.sort(function (a, b) {
        if (a.inst !== b.inst) { return b.inst - a.inst; }
        if (a.svc !== b.svc) { return b.svc - a.svc; }
        if (a.sys !== b.sys) { return b.sys - a.sys; }
        return a.letter < b.letter ? -1 : (a.letter > b.letter ? 1 : 0);
    });
    return c[0].letter + ':\\ai';
}
function bobFindAiRoot() {
    var sh = new ActiveXObject('WScript.Shell');
    var fso = new ActiveXObject('Scripting.FileSystemObject');
    var override = '';
    try { override = sh.ExpandEnvironmentStrings('%BOB_AI_ROOT%'); if (override === '%BOB_AI_ROOT%') { override = ''; } } catch (e1) { override = ''; }
    var sysDrive = 'C:';
    try { sysDrive = sh.ExpandEnvironmentStrings('%SystemDrive%'); if (sysDrive === '%SystemDrive%') { sysDrive = 'C:'; } } catch (e2) { }
    var products = ['bob', 'jeeves', 'airc', 'ergo'];
    var drives = [], e = new Enumerator(fso.Drives);
    for (; !e.atEnd(); e.moveNext()) {
        var dr = e.item();
        var d = { letter: String(dr.DriveLetter), type: dr.DriveType, hasAi: false, installs: 0 };
        if (d.type === 2) {
            try {
                var ai = d.letter + ':\\ai';
                if (fso.FolderExists(ai)) {
                    d.hasAi = true;
                    for (var k = 0; k < products.length; k++) { if (fso.FolderExists(ai + '\\' + products[k])) { d.installs++; } }
                }
            } catch (e3) { }
        }
        drives.push(d);
    }
    var letters = [], svcs = ['ircBob', 'ircJeeves', 'BobIrcd', 'Airc'];
    for (var s = 0; s < svcs.length; s++) {
        var keys = ['ImagePath', 'Parameters\\AppDirectory', 'Parameters\\Application'];
        for (var q = 0; q < keys.length; q++) {
            try {
                var v = sh.RegRead('HKLM\\SYSTEM\\CurrentControlSet\\Services\\' + svcs[s] + '\\' + keys[q]);
                var l = bobAiLetter(v);
                if (l) { letters.push(l); }
            } catch (e4) { }
        }
    }
    return bobPickAiRoot({ override: override, systemDrive: sysDrive, drives: drives, svcLetters: letters });
}
// MSI entry point (CustomAction JScriptCall="FindAiRoot"); tests load this file and call bobPickAiRoot / bobFindAiRoot directly.
function FindAiRoot() {
    Session.Property('AIROOT') = bobFindAiRoot();
    return 1;
}
