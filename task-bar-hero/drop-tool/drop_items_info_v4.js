'use strict';

var B = Process.enumerateModules().find(function(m) { return m.name.toLowerCase().indexOf('gameassembly') !== -1; }).base;
console.log('GameAssembly.dll @ ' + B);

// IL2CPP API (verified addresses from enumerateExports)
var dn = new NativeFunction(B.add(0x609aa0), 'pointer', []);
var daf = new NativeFunction(B.add(0x609ab0), 'pointer', ['pointer', 'pointer']);
var aif = new NativeFunction(B.add(0x5ecad0), 'pointer', ['pointer']);
var cfn = new NativeFunction(B.add(0x609760), 'pointer', ['pointer', 'pointer', 'pointer']);
var cmfn = new NativeFunction(B.add(0x609810), 'pointer', ['pointer', 'pointer', 'int']);
var cnf = new NativeFunction(B.add(0x609830), 'pointer', ['pointer']);

function cstr(s) { return Memory.allocUtf8String(s); }

// Find all target methods
var d = dn();
var sz = Memory.alloc(4);
var asms = daf(d, sz);
var cnt = sz.readU32();

var emptyNs = cstr('');
var found = {};

// Known class names: vw has jsq/jsl/jso, other class has iqg/iql
// First find vw methods
for (var a = 0; a < cnt; a++) {
    var asm = asms.add(a * Process.pointerSize).readPointer();
    if (!asm || asm.isNull()) continue;
    var img = aif(asm);
    if (!img || img.isNull()) continue;
    
    var k = cfn(img, emptyNs, cstr('vw'));
    if (!k || k.isNull()) continue;
    
    var targets = ['jsq', 'jsl', 'jso'];
    for (var ti = 0; ti < targets.length; ti++) {
        var m = cmfn(k, cstr(targets[ti]), -1);
        if (m && !m.isNull()) {
            var fp = m.readPointer();
            var rva = fp.sub(B).toInt32();
            found[targets[ti]] = fp;
            console.log('  vw.' + targets[ti] + ' @ RVA=0x' + rva.toString(16));
        }
    }
    break; // Found vw, done
}

// Now find iqg/iql by searching all classes
console.log('Searching for iqg/iql class...');
for (var a = 0; a < cnt; a++) {
    var asm = asms.add(a * Process.pointerSize).readPointer();
    if (!asm || asm.isNull()) continue;
    var img = aif(asm);
    if (!img || img.isNull()) continue;
    
    var iccf = new NativeFunction(B.add(0x609ea0), 'int', ['pointer']);
    var icf = new NativeFunction(B.add(0x609e90), 'pointer', ['pointer', 'int']);
    var cc = iccf(img);
    if (cc === 0 || cc > 10000) continue;
    
    for (var c = 0; c < cc; c++) {
        var k = icf(img, c);
        if (!k || k.isNull()) continue;
        var cn = cnf(k).readCString();
        if (!cn || cn.length > 6) continue;
        
        if (!found['iqg']) {
            var m = cmfn(k, cstr('iqg'), -1);
            if (m && !m.isNull()) {
                found['iqg'] = m.readPointer();
                console.log('  class "' + cn + '".iqg @ RVA=0x' + found['iqg'].sub(B).toInt32().toString(16));
                if (found['iql']) break;
            }
        }
        if (!found['iql']) {
            var m = cmfn(k, cstr('iql'), -1);
            if (m && !m.isNull()) {
                found['iql'] = m.readPointer();
                console.log('  class "' + cn + '".iql @ RVA=0x' + found['iql'].sub(B).toInt32().toString(16));
                if (found['iqg']) break;
            }
        }
    }
    if (found['iqg'] && found['iql']) break;
}

if (!found['iqg']) console.log('  iqg: NOT FOUND');
if (!found['iql']) console.log('  iql: NOT FOUND');

// ======== Hook setup ========
if (!found['jsq']) { console.log('ERROR: jsq not found'); Process.exit(1); }

var g_vw = null;
var g_dropCount = 0;
var g_boxOpenCount = 0;
var g_firstJsqSeen = false;
var g_queuesDisplayed = false;
var g_snapshots = new Map();

function now() { var d = new Date(); return '[' + d.toISOString().slice(11, 23) + ']'; }
function log(msg) { console.log(now() + ' ' + msg); }

function readBexlQueues() {
    if (!g_vw || g_vw.isNull()) return [];
    try {
        var bexl = g_vw.add(0x10).readPointer();
        if (!bexl || bexl.isNull()) return [];
        var ep = bexl.add(0x18).readPointer();
        var count = bexl.add(0x20).readS32();
        if (!ep || ep.isNull() || count <= 0) return [];
        var results = [];
        for (var i = 0; i < count; i++) {
            var entry = ep.add(0x20 + i * 24);
            var ebt = entry.add(0x08).readS32();
            var lp = entry.add(0x10).readPointer();
            if (!lp || lp.isNull()) continue;
            var arr = lp.add(0x10).readPointer();
            var sz = lp.add(0x18).readS32();
            if (!arr || arr.isNull() || sz <= 0) continue;
            var ids = [];
            for (var j = 0; j < Math.min(sz, 64); j++) {
                var bd = arr.add(0x20 + j * 8).readPointer();
                if (bd && !bd.isNull()) ids.push(bd.add(0x3C).readS32());
            }
            var label = ebt === 0 ? '\u666e\u901a\u6389\u843d' : ebt === 1 ? '\u9996\u9886\u6389\u843d' : ebt === 2 ? 'ACT\u6389\u843d' : '\u672a\u77e5(' + ebt + ')';
            results.push({ eboxType: ebt, label: label, items: ids, size: sz, listPtr: lp });
        }
        return results.sort(function(a,b) { return a.eboxType - b.eboxType; });
    } catch(e) { return []; }
}

function displayQueue(q) {
    log('  [' + q.label + ']  ' + q.items.length + '\u9879' + (q.items.length > 0 ? '  item[0]=' + q.items[0] : ''));
    var line = q.items.join(',');
    if (line.length <= 90) { log('    items=[' + line + ']'); }
    else { var half = Math.ceil(q.items.length / 2); log('    items=[' + q.items.slice(0, half).join(',')); log('           ' + q.items.slice(half).join(',') + ']'); }
    if (q.items.length > 0) log('    >> \u4e0b\u4e00\u4e2a: ' + q.items[0] + ' <<');
}

function showBexlQueues(source) {
    var queues = readBexlQueues();
    if (queues.length === 0) return false;
    var changed = false;
    for (var qi = 0; qi < queues.length; qi++) {
        var q = queues[qi];
        var key = 'bexl:' + q.eboxType;
        var old = g_snapshots.get(key);
        if (!old) { changed = true; break; }
        if (old.items.length !== q.items.length) { changed = true; break; }
        if (old.items.length > 0 && q.items.length > 0 && old.items[0] !== q.items[0]) { changed = true; break; }
    }
    if (g_queuesDisplayed && !changed) return true;
    g_snapshots.clear();
    for (var qi = 0; qi < queues.length; qi++) {
        var q = queues[qi];
        g_snapshots.set('bexl:' + q.eboxType, { eboxType: q.eboxType, label: q.label, items: q.items.slice(), size: q.size });
    }
    log('');
    log('[' + source + '] ' + queues.length + ' \u4e2a\u6389\u843d\u961f\u5217:');
    for (var qi = 0; qi < queues.length; qi++) { displayQueue(queues[qi]); }
    g_queuesDisplayed = true;
    return true;
}

// Hook jsq — 每次调用都检测 bexl 变化，不再依赖 jsl
Interceptor.attach(found['jsq'], {
    onEnter: function(args) {
        if (!g_vw || g_vw.isNull()) g_vw = args[0];
        if (!g_firstJsqSeen) {
            g_firstJsqSeen = true;
            showBexlQueues('\u542f\u52a8');
        } else {
            // 后续每次调用检测 bexl 是否变化
            var queues = readBexlQueues();
            if (queues.length > 0) {
                var changed = false;
                for (var qi = 0; qi < queues.length; qi++) {
                    var q = queues[qi];
                    var key = 'bexl:' + q.eboxType;
                    var old = g_snapshots.get(key);
                    if (!old) { changed = true; break; }
                    if (old.items.length !== q.items.length) { changed = true; break; }
                    if (old.items.length > 0 && q.items.length > 0 && old.items[0] !== q.items[0]) { changed = true; break; }
                }
                if (changed) {
                    showBexlQueues('\u5730\u56fe/\u66f4\u65b0');
                }
            }
        }
    },
    onLeave: function(ret) {
        if (ret && !ret.isNull()) {
            try {
                var itemId = ret.add(0x3C).readS32();
                g_dropCount++;
                log('  [\u6389\u843d #' + g_dropCount + '] \u9009\u4e2d: ' + itemId);
            } catch(e) {}
        }
    }
});
log('\u2713 Hooked jsq');

// Hook jsl — 仅记录日志，不干预快照（由 jsq 的数据变化检测处理）
if (found['jsl']) {
    Interceptor.attach(found['jsl'], {
        onEnter: function(args) {
            if (!g_vw || g_vw.isNull()) g_vw = args[0];
            log('\n========================================');
            log('=== \u8fdb\u5165\u65b0\u5730\u56fe ===');
            log('========================================');
        }
    });
    log('\u2713 Hooked jsl');
}

// Hook jso
if (found['jso']) {
    Interceptor.attach(found['jso'], {
        onLeave: function(ret) {
            if (ret && !ret.isNull()) {
                try { log('  [jso] \u79fb\u9664 BoxData: rewardItemId=' + ret.add(0x68).readS32()); } catch(e) {}
            }
            showBexlQueues('\u5f00\u7bb1');
        }
    });
    log('\u2713 Hooked jso');
}

// Hook iqg
if (found['iqg']) {
    Interceptor.attach(found['iqg'], {
        onEnter: function(args) {
            g_boxOpenCount++;
            log('\n--- [\u5f00\u7bb1 #' + g_boxOpenCount + '] ---');
        }
    });
    log('\u2713 Hooked iqg');
}

// Hook iql
if (found['iql']) {
    Interceptor.attach(found['iql'], {
        onEnter: function(args) {
            try { log('  [\u53d1\u5956] rewardItemId=' + args[0].add(0x68).readS32()); } catch(e) {}
        }
    });
    log('\u2713 Hooked iql');
}

log('\n=== Drop Items Info v4 \u5c31\u7eea ===');
