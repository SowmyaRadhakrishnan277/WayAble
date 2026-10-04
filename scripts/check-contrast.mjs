const themes={
 light:{bg:'#f2faf8',surface:'#ffffff',ink:'#102a2a',muted:'#405958',liffey:'#08727b',tactile:'#f1b42d',ok:'#137a51',okBg:'#e4f5ec',barrier:'#b42318',barrierBg:'#fff0ee',unknown:'#865700',unknownBg:'#fff5df',reported:'#663399',reportedBg:'#f4edfb'},
 dark:{bg:'#131817',surface:'#1c2422',ink:'#f4f5f2',muted:'#bdc6c2',liffey:'#63c0c5',ok:'#7ce3a0',okBg:'#18231d',barrier:'#ff8a80',barrierBg:'#291716',unknown:'#ffc266',unknownBg:'#282116',reported:'#d7b8ff',reportedBg:'#211a2b'},
 contrast:{bg:'#000000',surface:'#000000',ink:'#ffffff',muted:'#ffffff',liffey:'#ffd60a',ok:'#7ce3a0',okBg:'#000000',barrier:'#ff8a80',barrierBg:'#000000',unknown:'#ffc266',unknownBg:'#000000',reported:'#d7b8ff',reportedBg:'#000000'}
};
function lum(hex){const c=hex.replace('#','').match(/.{2}/g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return .2126*c[0]+.7152*c[1]+.0722*c[2]}
function ratio(a,b){const [hi,lo]=[lum(a),lum(b)].sort((x,y)=>y-x);return(hi+.05)/(lo+.05)}
const pairs=[['ink','bg'],['muted','bg'],['liffey','bg'],['ink','surface'],['muted','surface'],['ok','okBg'],['barrier','barrierBg'],['unknown','unknownBg'],['reported','reportedBg']];let failed=false;
for(const [name,t] of Object.entries(themes)){for(const [fg,bg] of pairs){if(!t[fg]||!t[bg])continue;const r=ratio(t[fg],t[bg]);if(r<4.5){failed=true;console.error(`${name}: ${fg} on ${bg} = ${r.toFixed(2)}:1 (needs 4.5:1)`)}else console.log(`${name}: ${fg} on ${bg} ${r.toFixed(2)}:1`)}}
if(failed)process.exit(1);console.log('All checked text pairs meet 4.5:1.');
