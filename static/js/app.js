/* 全局小工具脚本 */
(function(){
  // 自动消失的 flash 提示
  document.querySelectorAll('.flash').forEach(function(el){
    setTimeout(function(){
      el.style.transition='opacity .4s'; el.style.opacity='0';
      setTimeout(function(){ el.remove(); }, 450);
    }, 4000);
  });

  // ============ 高级备件选择器（出入库申请 / 出入库管理 / 调库管理 共用） ============
  // 用法：
  //   <input type="hidden" name="part_id" id="xxx-part-id">
  //   <button type="button" class="btn" onclick="PartPicker.show('xxx-part-id','xxx-part-name')">🔍 选择备件…</button>
  //   <span id="xxx-part-name" class="muted">未选择</span>
  // 说明：支持按 料号/名称/规格/分类 关键词即时搜索，避免千级备件下拉选择困难。
  var mask = null, curInput = null, curName = null, timer = null, curCallback = null;

  function ensure(){
    if(mask) return;
    mask = document.createElement('div');
    mask.className = 'modal-mask';
    mask.style.display = 'none';
    mask.addEventListener('click', function(e){ if(e.target === mask) hide(); });
    mask.innerHTML =
      '<div class="modal">' +
        '<div class="modal-head"><span>' + TR('选择备件') + '（' + TR('支持按') + ' ' + TR('料号') + ' / ' + TR('名称') + ' / ' + TR('规格') + ' ' + TR('搜索') + '）</span>' +
          '<button type="button" class="modal-x" onclick="PartPicker.hide()">✕</button></div>' +
        '<div class="modal-body">' +
          '<div class="inline-form" style="margin-bottom:10px">' +
            '<input class="f-input picker-kw" placeholder="' + TR('输入') + ' ' + TR('料号') + ' / ' + TR('名称') + ' / ' + TR('规格') + ' ' + TR('关键词') + '…" style="flex:1;min-width:220px">' +
            '<button type="button" class="btn btn-primary picker-go">' + TR('搜索') + '</button>' +
            '<span class="muted small">' + TR('共') + ' <b class="picker-count">0</b> ' + TR('条') + '（' + TR('输入即搜') + '）</span>' +
          '</div>' +
          '<div class="table-wrap" style="max-height:52vh;overflow-y:auto">' +
            '<table class="table"><thead><tr><th>' + TR('料号') + '</th><th>' + TR('名称') + '</th><th>' + TR('规格') + '</th><th>' + TR('库存') + '</th><th>' + TR('单价') + '(元)</th><th>' + TR('贵重') + '</th><th>' + TR('操作') + '</th></tr></thead>' +
            '<tbody class="picker-rows"><tr><td colspan="7" class="muted center">' + TR('输入关键词搜索，或直接点击「搜索」列出全部备件') + '</td></tr></tbody>' +
          '</table></div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(mask);
    var kw = mask.querySelector('.picker-kw');
    var go = mask.querySelector('.picker-go');
    function doSearch(){ search(kw.value); }
    kw.addEventListener('input', function(){ clearTimeout(timer); timer = setTimeout(doSearch, 300); });
    kw.addEventListener('keydown', function(e){ if(e.key === 'Enter'){ e.preventDefault(); doSearch(); } });
    go.addEventListener('click', doSearch);
  }

  function search(kw){
    var url = '/api/parts/search?kw=' + encodeURIComponent(kw || '') + '&limit=60';
    fetch(url).then(function(r){ return r.json(); }).then(function(list){
      var tb = mask.querySelector('.picker-rows');
      mask.querySelector('.picker-count').textContent = list.length;
      if(!list.length){ tb.innerHTML = '<tr><td colspan="7" class="muted center">' + TR('没有匹配的备件') + '</td></tr>'; return; }
      var html = '';
      list.forEach(function(p){
        html += '<tr>' +
          '<td class="mono">' + esc(p.part_code) + '</td>' +
          '<td>' + esc(p.name) + '</td>' +
          '<td class="mono">' + esc(p.spec || '-') + '</td>' +
          '<td class="num">' + esc(p.stock) + ' ' + esc(p.unit) + '</td>' +
          '<td class="num">' + esc(p.unit_price) + '</td>' +
          '<td>' + (p.is_valuable ? '<span class="badge badge-val">' + TR('贵重') + '</span>' : '-') + '</td>' +
          '<td><button type="button" class="btn btn-xs btn-primary" data-id="' + p.id + '" data-code="' + esc(p.part_code) + '" data-name="' + esc(p.name) + '" data-dec="' + (p.qty_decimal||0) + '" data-unit="' + esc(p.unit||'') + '" data-stock="' + esc(p.stock||0) + '" data-val="' + (p.is_valuable||0) + '">' + TR('选择') + '</button></td>' +
          '</tr>';
      });
      tb.innerHTML = html;
      tb.querySelectorAll('button[data-id]').forEach(function(btn){
        btn.addEventListener('click', function(){
          var input = document.getElementById(curInput);
          if(input) input.value = btn.getAttribute('data-id');
          var nameEl = document.getElementById(curName);
          if(nameEl) nameEl.textContent = btn.getAttribute('data-code') + '｜' + btn.getAttribute('data-name');
          var p = {
            id: Number(btn.getAttribute('data-id')),
            part_code: btn.getAttribute('data-code'),
            name: btn.getAttribute('data-name'),
            qty_decimal: Number(btn.getAttribute('data-dec') || 0),
            unit: btn.getAttribute('data-unit') || '',
            stock: Number(btn.getAttribute('data-stock') || 0),
            is_valuable: Number(btn.getAttribute('data-val') || 0)
          };
          hide();
          if(typeof curCallback === 'function'){ var cb = curCallback; curCallback = null; cb(p); }
        });
      });
    }).catch(function(){
      mask.querySelector('.picker-rows').innerHTML = '<tr><td colspan="7" class="muted center">' + TR('搜索失败，请重试') + '</td></tr>';
    });
  }

  function show(inputId, nameId, onPick){
    curInput = inputId; curName = nameId; curCallback = onPick || null;
    ensure();
    mask.style.display = 'flex';
    var kw = mask.querySelector('.picker-kw');
    kw.value = '';
    kw.focus();
    search('');
  }

  function hide(){ if(mask) mask.style.display = 'none'; }

  window.PartPicker = { show: show, hide: hide };

  function esc(s){ var d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
})();
