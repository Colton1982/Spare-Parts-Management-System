/* 轻量 Canvas 图表（无外部依赖，内网离线可用）
 * drawBars / drawLines / drawPie 三个函数。
 * 可选 opts（大屏深色时传入）：
 *   { font, text, grid, line, sub, value, bg }
 */
(function(){
  const tip = document.createElement('div');
  tip.style.cssText = 'position:fixed;background:rgba(17,24,39,.92);color:#fff;padding:6px 10px;'+
    'border-radius:6px;font-size:12px;pointer-events:none;display:none;z-index:9999;white-space:nowrap;';
  document.body.appendChild(tip);

  function showTip(x, y, html){
    tip.innerHTML = html;
    tip.style.display = 'block';
    let tx = x + 14, ty = y - 8;
    if(tx + tip.offsetWidth > window.innerWidth) tx = x - tip.offsetWidth - 10;
    if(ty < 8) ty = 8;
    tip.style.left = tx + 'px'; tip.style.top = ty + 'px';
  }
  function hideTip(){ tip.style.display = 'none'; }

  function setup(canvas){
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || canvas.parentElement.clientWidth;
    const h = canvas.clientHeight || 260;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return {ctx, w, h};
  }

  const D = {
    font: 12, text: '#475569', grid: '#eef1f5', line: '#dde3ea',
    bottomVal: false,
    sub: '#6b7280', value: '#6b7280', bg: '#ffffff'
  };
  // 默认彩色色板（避免数据未带颜色时画出白/灰柱子）
  const PALETTE = ['#3b82f6','#22c55e','#8b5cf6','#06b6d4','#f59e0b','#ec4899','#84cc16','#14b8a6','#6366f1','#0ea5e9'];
  function opt(o, k){ return o && o[k] !== undefined ? o[k] : D[k]; }

  function niceMax(v){
    if(v <= 0) return 1;
    const exp = Math.pow(10, Math.floor(Math.log10(v)));
    const f = v / exp;
    const nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
    return nf * exp;
  }

  function axesStyle(ctx, o){
    ctx.font = opt(o,'font') + 'px "Microsoft YaHei",sans-serif';
  }

  window.drawBars = function(id, labels, series, o){
    const canvas = document.getElementById(id);
    if(!canvas || !labels.length) return;
    const {ctx, w, h} = setup(canvas);
    const font = opt(o,'font'), sub = opt(o,'sub'), text = opt(o,'text'),
          grid = opt(o,'grid'), line = opt(o,'line');
    const n = labels.length;
    // 横轴标签：表格样式——每个柱位下方水平换行完整显示标签；可选底部数值行（bottomVal，默认开）
    const lf = font, lineH = lf + 7, bottomVal = opt(o,'bottomVal') !== false;
    const maxLen = Math.max.apply(null, labels.map(function(l){ return Math.max.apply(null, String(l).split('\n').map(function(s){ return s.length; })); }));
    const cpl = Math.max(2, Math.floor(((w - 68) / n - 10) / (lf * 0.62)));   // 每行最多字符数
    const maxLines = Math.max(1, Math.ceil(maxLen / cpl));
    let bRot = 10 + maxLines * lineH + lf + (bottomVal ? 18 : 14);            // 标签区更高，多行标签不拥挤
    bRot = Math.max(34, Math.min(bRot, Math.floor(h * 0.45)));
    const M = {l: 52, r: 16, t: 24 + (font-11)*2, b: bRot};
    const pw = w - M.l - M.r, ph = h - M.t - M.b;
    const max = niceMax(Math.max(1, ...series.flatMap(s=>s.data)));
    ctx.font = font + 'px "Microsoft YaHei",sans-serif';
    for(let i=0;i<=4;i++){
      const v = max*i/4, y = M.t + ph - ph*i/4;
      ctx.strokeStyle = grid; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(M.l, y); ctx.lineTo(w-M.r, y); ctx.stroke();
      ctx.fillStyle = text; ctx.textAlign = 'right';
      ctx.fillText(fmtNum(v), M.l-8, y+font*0.4);
    }
    ctx.strokeStyle = line;
    ctx.beginPath(); ctx.moveTo(M.l, M.t+ph); ctx.lineTo(w-M.r, M.t+ph); ctx.stroke();
    const groupW = pw/n, slotW = groupW / series.length;
    // 标签表格：每柱位下方水平居中、自动换行完整显示；底部一行数值（悬停 tooltip 显示全名）
    ctx.fillStyle = text; ctx.textAlign = 'center';
    ctx.font = lf + 'px "Microsoft YaHei",sans-serif';
    // 按空格断词换行，优先保持"名称 规格"完整成词；超长词再按字符硬切
    const wrapLines = function(txt){
      const lines = [];
      String(txt).split('\n').forEach(function(seg){
        if(!seg){ lines.push(''); return; }
        const words = String(seg).split(/(\s+)/);
        let cur = '';
        words.forEach(function(w){
          if(!w) return;
          if(/^\s+$/.test(w)){ cur += w; return; }          // 保留词间空格
          const test = cur + w;
          if(cur && ctx.measureText(test).width > groupW - 10){ lines.push(cur.trim()); cur = w; }
          else cur = test;
        });
        if(cur.trim()) lines.push(cur.trim());
        // 超长词按字符硬切，保证不溢出列宽
        for(let li=0; li<lines.length; li++){
          let l = lines[li];
          while(ctx.measureText(l).width > groupW - 10){
            let cut = l.length - 1;
            while(cut > 0 && ctx.measureText(l.slice(0, cut)).width > groupW - 10) cut--;
            if(cut <= 0) break;
            lines.splice(li + 1, 0, l.slice(cut));
            l = l.slice(0, cut); lines[li] = l;
          }
        }
      });
      return lines;
    };
    labels.forEach((lb,i)=>{
      const cx = M.l + groupW*i + groupW/2;
      const lines = wrapLines(lb);
      const startY = h - bRot + 8;
      lines.forEach(function(ln, li){
        ctx.fillText(ln, cx, startY + li*lineH + lf);
      });
    });
    // 底部数值行（各柱位合计，可关闭避免遮挡标签）
    if(bottomVal){
      ctx.fillStyle = sub;
      labels.forEach(function(lb,i){
        const cx = M.l + groupW*i + groupW/2;
        const v = series.reduce(function(s,se){ return s + (se.data[i]||0); }, 0);
        ctx.fillText(fmtNum(v), cx, h - 4);
      });
    }
    ctx.fillStyle = text; ctx.textAlign = 'right';
    series.forEach((s, si)=>{
      const sColor = s.color || PALETTE[si % PALETTE.length];
      s.data.forEach((v,i)=>{
        const x = M.l + groupW*i + slotW*si + slotW*0.15;
        const bh = (v/max)*ph;
        const y = M.t + ph - bh;
        ctx.fillStyle = sColor;
        ctx.fillRect(x, y, slotW*0.7, bh);
        if(v>0){ ctx.fillStyle = sub; ctx.textAlign='center'; ctx.font=font+'px sans-serif';
          const vy = Math.max(M.t+font+6, Math.min(y-4, h - bRot + 6)); // 防上裁、防落入标签区
          ctx.fillText(fmtNum(v), x+slotW*0.35, vy); }
      });
    });
    legend(ctx, w, series.map(s=>({name:s.name, color:s.color})), font, sub);
    canvas.onmousemove = e=>{
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left, y = e.clientY - rect.top;
      let hit = null;
      series.forEach((s, si)=>{
        s.data.forEach((v,i)=>{
          const bx = M.l + groupW*i + slotW*si + slotW*0.15;
          if(x>=bx && x<=bx+slotW*0.7 && y<=M.t+ph && y>=M.t){
            hit = {i, si, v, lb: labels[i], name: s.name};
          }
        });
      });
      if(hit){
        canvas.style.cursor='pointer';
        showTip(e.clientX, e.clientY, '<b>'+esc(hit.lb)+'</b> '+esc(hit.name)+'：'+fmtNum(hit.v));
      } else { canvas.style.cursor='default'; hideTip(); }
    };
    canvas.onmouseleave = hideTip;
  };

  window.drawLines = function(id, labels, series, o){
    const canvas = document.getElementById(id);
    if(!canvas || !labels.length) return;
    const {ctx, w, h} = setup(canvas);
    const font = opt(o,'font'), text = opt(o,'text'), grid = opt(o,'grid'),
          line = opt(o,'line'), sub = opt(o,'sub'), value = opt(o,'value');
    const n = labels.length;
    // 折线图横轴标签：与柱状图一致——每个点下方水平换行完整显示；可选底部数值行
    const lf = font, lineH = lf + 7, bottomVal = opt(o,'bottomVal') !== false;
    const maxLen = Math.max.apply(null, labels.map(function(l){ return Math.max.apply(null, String(l).split('\n').map(function(s){ return s.length; })); }));
    const cpl = Math.max(2, Math.floor(((w - 68) / n - 10) / (lf * 0.62)));
    const maxLines = Math.max(1, Math.ceil(maxLen / cpl));
    let bRot = 10 + maxLines * lineH + lf + (bottomVal ? 18 : 14);
    bRot = Math.max(34, Math.min(bRot, Math.floor(h * 0.45)));
    const M = {l: 52, r: 16, t: 24 + (font-11)*2, b: bRot};
    const pw = w - M.l - M.r, ph = h - M.t - M.b;
    const max = niceMax(Math.max(1, ...series.flatMap(s=>s.data)));
    ctx.font = font + 'px "Microsoft YaHei",sans-serif';
    for(let i=0;i<=4;i++){
      const v = max*i/4, y = M.t + ph - ph*i/4;
      ctx.strokeStyle = grid; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(M.l, y); ctx.lineTo(w-M.r, y); ctx.stroke();
      ctx.fillStyle = text; ctx.textAlign = 'right';
      ctx.fillText(fmtNum(v), M.l-8, y+font*0.4);
    }
    ctx.strokeStyle = line;
    ctx.beginPath(); ctx.moveTo(M.l, M.t+ph); ctx.lineTo(w-M.r, M.t+ph); ctx.stroke();
    const step = pw/(n-1||1);
    // 标签表格：每点下方水平居中、自动换行完整显示；底部一行数值
    ctx.fillStyle = text; ctx.textAlign = 'center';
    ctx.font = lf + 'px "Microsoft YaHei",sans-serif';
    // 按空格断词换行，优先保持"名称 规格"完整成词；超长词再按字符硬切
    const wrapLines = function(txt){
      const lines = [];
      String(txt).split('\n').forEach(function(seg){
        if(!seg){ lines.push(''); return; }
        const words = String(seg).split(/(\s+)/);
        let cur = '';
        words.forEach(function(w){
          if(!w) return;
          if(/^\s+$/.test(w)){ cur += w; return; }          // 保留词间空格
          const test = cur + w;
          if(cur && ctx.measureText(test).width > step - 8){ lines.push(cur.trim()); cur = w; }
          else cur = test;
        });
        if(cur.trim()) lines.push(cur.trim());
        for(let li=0; li<lines.length; li++){
          let l = lines[li];
          while(ctx.measureText(l).width > step - 8){
            let cut = l.length - 1;
            while(cut > 0 && ctx.measureText(l.slice(0, cut)).width > step - 8) cut--;
            if(cut <= 0) break;
            lines.splice(li + 1, 0, l.slice(cut));
            l = l.slice(0, cut); lines[li] = l;
          }
        }
      });
      return lines;
    };
    labels.forEach((lb,i)=>{
      const cx = M.l + step*i;
      const lines = wrapLines(lb);
      const startY = h - bRot + 8;
      lines.forEach(function(ln, li){
        ctx.fillText(ln, cx, startY + li*lineH + lf);
      });
    });
    if(bottomVal){
      ctx.fillStyle = sub;
      labels.forEach(function(lb,i){
        const cx = M.l + step*i;
        const v = series.reduce(function(s,se){ return s + (se.data[i]||0); }, 0);
        ctx.fillText(fmtNum(v), cx, h - 4);
      });
    }
    ctx.fillStyle = text; ctx.textAlign = 'right';
    const pts = [];
    series.forEach((s, si)=>{
      const sColor = s.color || PALETTE[si % PALETTE.length];
      ctx.strokeStyle = sColor; ctx.lineWidth = 2; ctx.beginPath();
      s.data.forEach((v,i)=>{
        const x = M.l+step*i, y = M.t+ph-(v/max)*ph;
        i===0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
        pts.push({x, y, v, i, name:s.name, lb:labels[i]});
      });
      ctx.stroke();
      ctx.fillStyle = sColor;
      s.data.forEach((v,i)=>{
        ctx.beginPath(); ctx.arc(M.l+step*i, M.t+ph-(v/max)*ph, 3, 0, Math.PI*2); ctx.fill();
      });
      // 数据点上方数值标注（防止贴近上边界被裁剪）
      ctx.fillStyle = value; ctx.textAlign = 'center';
      s.data.forEach((v,i)=>{
        const x = M.l+step*i, y = M.t+ph-(v/max)*ph;
        const vy = Math.max(M.t+font+6, Math.min(y-4, h - bRot + 6));
        ctx.fillText(fmtNum(v), x, vy);
      });
    });
    legend(ctx, w, series.map(s=>({name:s.name, color:s.color||PALETTE[0]})), font, sub);
    canvas.onmousemove = e=>{
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX-rect.left;
      let best=null, bd=1e9;
      pts.forEach(p=>{
        const d = Math.abs(p.x-x);
        if(d<bd){ bd=d; best=p; }
      });
      if(best && bd < step*0.6){
        canvas.style.cursor='pointer';
        showTip(e.clientX, e.clientY, '<b>'+esc(best.lb)+'</b> '+esc(best.name)+'：'+fmtNum(best.v));
      } else { canvas.style.cursor='default'; hideTip(); }
    };
    canvas.onmouseleave = hideTip;
  };

  window.drawPie = function(id, data, o){
    const canvas = document.getElementById(id);
    if(!canvas) return;
    const {ctx, w, h} = setup(canvas);
    const font = opt(o,'font'), text = opt(o,'text'), sub = opt(o,'sub');
    const total = data.reduce((s,d)=>s+d.value, 0);
    if(total<=0){
      ctx.fillStyle=text; ctx.textAlign='center'; ctx.font=font+'px sans-serif';
      ctx.fillText(TR('暂无数据'), w/2, h/2);
      return;
    }
    const colors = (o && o.colors && o.colors.length) ? o.colors :
      ['#2563eb','#22c55e','#f97316','#8b5cf6','#06b6d4','#ef4444','#eab308','#14b8a6','#f472b6','#64748b'];
    const cx = w*0.38, cy = h/2, R = Math.min(h/2-14, 110);
    let a0 = -Math.PI/2;
    const slices = [];
    data.forEach((d, i)=>{
      const a1 = a0 + (d.value/total)*Math.PI*2;
      ctx.beginPath(); ctx.moveTo(cx,cy); ctx.arc(cx,cy,R,a0,a1); ctx.closePath();
      ctx.fillStyle = colors[i%colors.length]; ctx.fill();
      ctx.strokeStyle='#fff'; ctx.lineWidth=2; ctx.stroke();
      slices.push({a0,a1,d,color:colors[i%colors.length]});
      a0 = a1;
    });
    let ly = 26 + (font-11)*2;
    ctx.textAlign='left'; ctx.font=font+'px "Microsoft YaHei",sans-serif';
    data.forEach((d,i)=>{
      const color = colors[i%colors.length];
      ctx.fillStyle = color; ctx.fillRect(w*0.55, ly-10, 12, 12);
      ctx.fillStyle = sub;
      const pct = total? (d.value/total*100).toFixed(1):0;
      ctx.fillText(esc(d.name) + '  ' + fmtNum(d.value) + ' (' + pct + '%)', w*0.55+18, ly);
      ly += 22 + (font-11)*1.2;
    });
    canvas.onmousemove = e=>{
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX-rect.left, y = e.clientY-rect.top;
      const dx=x-cx, dy=y-cy;
      if(Math.hypot(dx,dy)<=R){
        let ang = Math.atan2(dy,dx);
        if(ang < -Math.PI/2) ang += Math.PI*2;
        const hit = slices.find(s=>ang>=s.a0 && ang<s.a1) || slices[slices.length-1];
        if(hit){
          canvas.style.cursor='pointer';
          showTip(e.clientX, e.clientY, '<b>'+esc(hit.d.name)+'</b>：'+fmtNum(hit.d.value)+' '+TR('元')+' ('+
            (hit.d.value/total*100).toFixed(1)+'%)');
        }
      } else { canvas.style.cursor='default'; hideTip(); }
    };
    canvas.onmouseleave = hideTip;
  };

  function legend(ctx, w, items, font, color){
    // 多语言下标签长度差异大：先测总宽，超宽则自动缩小字号，避免标签重叠/裁切
    ctx.font = font + 'px "Microsoft YaHei",sans-serif';
    let need = 20;
    for(let i=0;i<items.length;i++) need += ctx.measureText(items[i].name).width + 22;
    if(need > w && items.length){
      font = Math.max(9, Math.floor(font * (w - 24) / need));
      ctx.font = font + 'px "Microsoft YaHei",sans-serif';
    }
    let x = w - 20;
    ctx.textAlign = 'right';
    for(let i=items.length-1;i>=0;i--){
      const t = items[i].name;
      const tw = ctx.measureText(t).width;
      x -= tw;
      ctx.fillStyle = items[i].color || PALETTE[i % PALETTE.length];
      ctx.fillRect(x-12, 8, 10, 10);
      ctx.fillStyle = color;
      ctx.fillText(t, x-16, 17);
      x -= 22;
    }
  }
  function fmtNum(v){
    v = Number(v||0);
    if(Math.abs(v)>=10000) return (v/10000).toFixed(1)+TR('万');
    return v.toLocaleString('zh-CN');
  }
  function esc(s){ const d=document.createElement('div'); d.textContent=s==null?'':String(s); return d.innerHTML; }
})();
