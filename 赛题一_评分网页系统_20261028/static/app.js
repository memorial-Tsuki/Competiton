'use strict';
let config, lastResult=null, lastPayload=null, busy=false, dirty=false, exampleNote='', experienceStage='cover', progressTimer=null, customerType='existing';
const $=id=>document.getElementById(id);
const fmt=(n,d=2)=>Number(n).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
const signed=n=>(n>0?'+':'')+fmt(n);
const pct=n=>fmt(n*100)+'%';
const text=(id,value)=>{$(id).textContent=value;};
function showError(message){text('global-error',message);$('global-error').classList.remove('hidden');$('global-error').scrollIntoView({behavior:'smooth',block:'nearest'});}
function clearError(){$('global-error').classList.add('hidden');}
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function setExperienceStage(stage,scroll=true){
  experienceStage=stage;document.body.dataset.experienceStage=stage;
  document.querySelectorAll('[data-stage-jump]').forEach(button=>{
    const active=button.dataset.stageJump===stage;button.classList.toggle('active',active);button.setAttribute('aria-current',active?'step':'false');
    button.disabled=button.dataset.stageJump==='output'&&!lastResult;
  });
  if(stage==='input'){setStep('input',false);if(scroll)$('assessment').scrollIntoView({behavior:'smooth',block:'start'});}
  if(stage==='output'&&scroll)$('assessment').scrollIntoView({behavior:'smooth',block:'start'});
}
function setProgress(value,title,copy){
  text('progress-value',Math.round(value)+'%');$('progress-fill').style.width=Math.max(0,Math.min(100,value))+'%';
  if(title)text('progress-title',title);if(copy)text('progress-copy',copy);
  document.querySelectorAll('.progress-steps span').forEach((step,index)=>step.classList.toggle('active',value>index*34));
}
function beginProgress(){
  $('score-progress').classList.remove('hidden');setProgress(8,'正在校验客户输入','检查必填项、参考额度和数据范围。');
  let value=8;clearInterval(progressTimer);progressTimer=setInterval(()=>{value=Math.min(88,value+(value<38?8:4));if(value<38)setProgress(value,'正在校验客户输入','检查必填项、参考额度和数据范围。');else if(value<70)setProgress(value,'正在计算风险评分','冻结模型正在本机生成参考评分与风险概率。');else setProgress(value,'正在整理结果解读','正在生成完整度提示、复核原因与情景分析。');},105);
}
async function finishProgress(){clearInterval(progressTimer);setProgress(100,'评分已完成','结果、简要分析和情景入口已准备完成。');await wait(360);$('score-progress').classList.add('hidden');}
function stopProgress(){clearInterval(progressTimer);$('score-progress').classList.add('hidden');}
function option(value,label){const o=document.createElement('option');o.value=value;o.textContent=label;return o;}
function buildFields(){
  for(const [id,title,hint] of config.groups){
    const group=document.createElement(id==='current'?'section':'details');group.className='form-group';group.dataset.group=id;
    const header=document.createElement(id==='current'?'h3':'summary');header.textContent=title;
    const fields=config.fields.filter(f=>f.group===id);
    if(id!=='current'){const s=document.createElement('span');s.className='optional-count';s.textContent=fields.length+' 项选填';header.append(s);}
    group.append(header);const p=document.createElement('p');p.className='group-intro';p.textContent=hint;group.append(p);
    const grid=document.createElement('div');grid.className='field-grid';
    for(const f of fields){
      const label=document.createElement('label');label.className='field';label.dataset.fieldKey=f.key;
      const title=document.createElement('span');title.textContent=f.label;title.dataset.defaultLabel=f.label;
      if(f.required){const mark=document.createElement('span');mark.textContent=' *';mark.className='required';title.append(mark);}
      label.append(title);
      const input=document.createElement(f.options?'select':'input');input.id='f-'+f.key;input.name=f.key;
      if(f.options){input.append(option('','未知 / 未提供'));for(const [v,t] of f.options)input.append(option(v,t));}
      else{input.type='number';input.step=f.integer?'1':'any';if(f.min!==null)input.min=f.min;if(f.max!==null)input.max=f.max;input.placeholder=f.required?'请填写':'未知留空';}
      input.required=f.required;label.append(input);
      if(f.hint){const h=document.createElement('small');h.className='hint';h.textContent=f.hint;h.dataset.defaultHint=f.hint;label.append(h);}
      grid.append(label);
    }
    group.append(grid);$('fields').append(group);
  }
  const optionalHeading=document.createElement('div');optionalHeading.className='optional-heading';optionalHeading.innerHTML='<span class=section-kicker>第二层 / 补充信息</span><h3>有资料时补充，未知时留空。</h3><p>展开对应类别，补全有依据的信息。没有外部评分也可演示，但不代表完成了去外部评分验证。</p>';$('fields').querySelector('details')?.before(optionalHeading);
  for(const s of config.scenarios)$('scenario-kind').append(option(s.id,s.label));
  for(const e of config.examples)$('example').append(option(e.id,e.label));
}
function setCustomerType(type,changed=true){
  customerType=type==='cold_start'?'cold_start':'existing';const cold=customerType==='cold_start';
  $('customer-form').dataset.customerType=customerType;
  document.querySelectorAll('.customer-type').forEach(button=>{const active=button.dataset.customerType===customerType;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
  const requiredKeys=new Set(cold?['AMT_INCOME_TOTAL','limit']:config.fields.filter(f=>f.required).map(f=>f.key));
  for(const f of config.fields){const label=document.querySelector(`.field[data-field-key="${f.key}"]`),input=$('f-'+f.key);const hide=cold&&(f.group==='history'||f.group==='applications'||['balance','drawings','payment','dpd','dpd_def'].includes(f.key));label.classList.toggle('cold-hidden',hide);input.required=requiredKeys.has(f.key);if(hide)input.value='';}
  document.querySelectorAll('.form-group').forEach(group=>group.classList.toggle('cold-hidden',cold&&['history','applications'].includes(group.dataset.group)));
  const current=document.querySelector('.form-group[data-group="current"]');current.querySelector('h3').textContent=cold?'首次授信信息':'当前授信与履约';current.querySelector('.group-intro').textContent=cold?'必填收入与拟定首次授信额度。客户尚未发生的余额、支用、付款和逾期由系统按 0 处理；未知历史保持缺失。':'必填。金额需与原始数据使用同一单位和口径；请勿混用月收入与其他收入周期。';
  const limitField=document.querySelector('.field[data-field-key="limit"]'),limitTitle=limitField.querySelector('span'),limitHint=limitField.querySelector('.hint');limitTitle.firstChild.data=cold?'拟定首次授信额度':'当前总授信额度';if(limitHint)limitHint.textContent=cold?'由使用者根据申请资料拟定；平台不自动推荐首次额度。':limitHint.dataset.defaultHint;
  $('required-badge').textContent=cold?'2 项必填':'7 项必填';$('cold-start-intro').classList.toggle('hidden',!cold);
  $('reference-box').classList.toggle('cold-start-reference',cold);$('cold-reference-note').classList.toggle('hidden',!cold);document.querySelector('input[name="reference-mode"][value="current"]').checked=true;referenceVisibility();
  for(const option of $('scenario-kind').options){option.hidden=cold&&option.value!=='pure_limit';option.disabled=cold&&option.value!=='pure_limit';}if(cold)$('scenario-kind').value='pure_limit';scenarioVisibility();
  if(changed)markDirty();
}
function scenarioVisibility(){const k=$('scenario-kind').value;for(const [cls,active] of [['limit',['pure_limit','combined'].includes(k)],['debt',['new_debt','combined'].includes(k)],['dpd',['ordinary_dpd','joint_dpd'].includes(k)],['payment',k==='payment']])document.querySelector('.scenario-'+cls).classList.toggle('hidden',!active);text('scenario-help',config.scenarios.find(s=>s.id===k)?.help||'');}
function markDirty(){dirty=true;if(lastResult)$('stale').classList.remove('hidden');$('export').disabled=true;$('print').disabled=true;updateProgress();}
function readPayload(){
  const inputs={};for(const f of config.fields){const v=$('f-'+f.key).value;inputs[f.key]=v===''?null:f.options?v:Number(v);}
  const mode=document.querySelector('input[name=reference-mode]:checked').value;
  const get=id=>$(id).value===''?null:Number($(id).value);
  return {customer_type:customerType,customer_label:$('customer-label').value.trim()||'未命名客户',inputs,reference:{mode,limit:get('reference-limit')},scenario:{kind:$('scenario-kind').value,limit_percent:get('scenario-limit'),debt_amount:get('scenario-debt'),dpd_days:get('scenario-dpd'),payment_amount:get('scenario-payment')}};
}
async function calculate(){
  if(busy)return;
  clearError();if(!$('customer-form').checkValidity()){setStep('input');const invalid=$('customer-form').querySelector(':invalid');if(invalid?.closest('details'))invalid.closest('details').open=true;$('customer-form').reportValidity();return;}
  for(const input of document.querySelectorAll('.scenario-controls input')){if(!input.closest('label').classList.contains('hidden')&&!input.reportValidity())return;}
  const payload=readPayload();busy=true;$('calculate').disabled=true;$('compare').disabled=true;$('calculate').textContent='正在计算…';beginProgress();
  // Changes made during a request must not be mistaken for the returned snapshot.
  const snapshot=JSON.stringify(payload);
  try{
    const response=await fetch('/api/score',{method:'POST',headers:{'Content-Type':'application/json','X-Score-Token':config.token},body:JSON.stringify(payload)});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'评分失败。');
    lastResult=data;lastPayload=payload;await finishProgress();render(data);
    dirty=snapshot!==JSON.stringify(readPayload());$('stale').classList.toggle('hidden',!dirty);$('export').disabled=dirty;$('print').disabled=dirty;updateProgress();setStep('result',false);setExperienceStage('output',true);
  }catch(error){stopProgress();showError(error.message||'无法连接评分服务，请重新启动。');}
  finally{busy=false;$('calculate').disabled=false;$('compare').disabled=false;$('calculate').textContent='计算信用评分 →';}
}
function list(id,items){const el=$(id);el.replaceChildren();for(const s of items){const li=document.createElement('li');li.textContent=s;el.append(li);}}
function render(r){
  $('empty-state').classList.add('hidden');$('results').classList.remove('hidden');
  const cold=r.customer_type==='cold_start';$('cold-start-result').classList.toggle('hidden',!cold);
  text('result-title',r.customer_label+' · 评分结果');text('result-time',new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})+' 本次计算');
  text('score',fmt(r.base.score));text('pd',pct(r.base.pd));text('live-score',fmt(r.base.live_score));text('score-caption',cold?'冷启动研究性估计；必须人工复核':'分数越高，模型估计风险越低');
  text('mechanical','较参考评分 '+signed(r.base.mechanical_limit_component_points)+' 分');
  const grades={A:'相对低风险',B:'较低风险',C:'中间风险',D:'较高风险',E:'高风险关注'};
  text('grade-pill',r.base.grade+' 级 · '+grades[r.base.grade]);text('gauge-grade',r.base.grade);
  $('gauge-fill').setAttribute('stroke-dashoffset',String(358.142*(1-(r.base.score-300)/550)));
  text('quality-count',r.quality.provided+' / '+r.quality.total+' 项由使用者提供');
  text('quality-summary',cold?'历史信息未被当作已提供数据；系统仅对尚未发生的当前行为使用 0，其余缺失沿用训练管线处理。':r.quality.missing.length?'存在选填信息缺失。数值填补沿用训练管线，结果需结合信息完整性阅读。':'所有界面输入均已提供；这不代表原始信息真实性已核验。');
  list('quality-notices',r.quality.notices);text('missing-fields',r.quality.missing.length?'未提供：'+r.quality.missing.join('、'):'');
  $('review').classList.toggle('hidden',!r.base.requires_review);list('review-list',r.base.review_messages.concat(r.base.outside_training_labels.length?['超范围字段：'+r.base.outside_training_labels.join('、')]:[]));
  text('before-score',fmt(r.base.score));text('after-score',fmt(r.scenario.score));text('delta-score',signed(r.scenario.reference_delta));
  text('scenario-pd','PD：'+pct(r.base.pd)+' → '+pct(r.scenario.pd)+'；等级：'+r.base.grade+' → '+r.scenario.grade+'；实时口径分：'+fmt(r.scenario.live_score)+'。');
  const changes=$('changed-fields');changes.replaceChildren();for(const f of r.scenario.changed_fields){const s=document.createElement('span');s.textContent=f.label+' '+fmt(f.before,2)+' → '+fmt(f.after,2);changes.append(s);}if(!changes.childNodes.length)changes.textContent='当前设置未改变输入。';
  $('scenario-review').classList.toggle('hidden',!r.scenario.requires_review);text('scenario-review',r.scenario.review_messages.join(' '));
  text('behavior-component',signed(r.scenario.risk_component_points));text('limit-component',signed(r.scenario.mechanical_limit_component_points));text('total-component',signed(r.scenario.total_change_points));
  chart('limit-chart',r.curves.limit,true,'%');chart('dpd-chart',r.curves.dpd,false,'天');
  text('scope',r.scope+' 图中横轴是输入变化，不是真实时间。');
  $('example-note').classList.toggle('hidden',!exampleNote);text('example-note',exampleNote);
}
function chart(id,rows,dual,suffix){
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 350 200');svg.setAttribute('role','img');svg.setAttribute('aria-label',dual?'纯提额情况下参考和实时评分曲线':'普通逾期增加情况下参考评分曲线');
  const values=rows.flatMap(r=>dual?[r.reference,r.live]:[r.reference]);let lo=Math.min(...values),hi=Math.max(...values);const pad=Math.max((hi-lo)*.18,3);lo-=pad;hi+=pad;
  const X=x=>42+(x/rows.at(-1).x)*290,Y=y=>156-(y-lo)/(hi-lo)*122;
  const add=(tag,attrs,content)=>{const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(content!==undefined)e.textContent=content;svg.append(e);return e;};
  for(let i=0;i<4;i++){const value=lo+(hi-lo)*i/3,y=Y(value);add('line',{x1:42,x2:332,y1:y,y2:y,stroke:'#34343e'});add('text',{x:35,y:y+3,'text-anchor':'end',fill:'#7b8d83','font-size':9},value.toFixed(1));}
  const ticks=dual?[0,20,50,100]:[0,7,30,60,90];for(const x of ticks)add('text',{x:X(x),y:177,'text-anchor':'middle',fill:'#7b8d83','font-size':9},x+suffix);
  add('text',{x:42,y:15,fill:'#7b8d83','font-size':9},'评分（局部纵轴）');
  if(dual)draw('live','#abb4ca');draw('reference','#ff6571');
  function draw(key,color){add('polyline',{points:rows.map(r=>X(r.x)+','+Y(r[key])).join(' '),fill:'none',stroke:color,'stroke-width':2.5,'stroke-linejoin':'round'});for(const r of rows){const c=add('circle',{cx:X(r.x),cy:Y(r[key]),r:3,fill:'#17171e',stroke:color,'stroke-width':1.5});const t=document.createElementNS(ns,'title');t.textContent=r.x+suffix+'：'+fmt(r[key])+' 分';c.append(t);}}
  $(id).replaceChildren(svg);
}
function fill(payload){
  if(!payload||typeof payload.inputs!=='object')throw new Error('文件缺少 inputs 客户信息。');
  const unknown=Object.keys(payload.inputs).filter(k=>!config.fields.some(f=>f.key===k));if(unknown.length)throw new Error('文件含不支持的输入字段：'+unknown.join('、'));
  for(const f of config.fields){const v=payload.inputs[f.key];if(v!=null&&f.options&&!f.options.some(o=>o[0]===v))throw new Error(f.label+'类别不受支持。');}
  $('customer-form').reset();setCustomerType(payload.customer_type==='cold_start'?'cold_start':'existing',false);
  for(const f of config.fields)$('f-'+f.key).value=payload.inputs[f.key]??'';
  $('customer-label').value=payload.customer_label||'';
  const mode=payload.reference?.mode==='fixed'?'fixed':'current';document.querySelector('input[name=reference-mode][value='+mode+']').checked=true;
  $('reference-limit').value=payload.reference?.limit??'';referenceVisibility();
  const s=payload.scenario||{};$('scenario-kind').value=s.kind||'pure_limit';$('scenario-limit').value=s.limit_percent??50;$('scenario-debt').value=s.debt_amount??10000;$('scenario-dpd').value=s.dpd_days??30;$('scenario-payment').value=s.payment_amount??1000;
  scenarioVisibility();exampleNote=payload.example_note||'';setStep('input',false);markDirty();
}
async function loadExample(key){if(!key)return showError('请先选择一个公开案例。');try{clearError();const r=await fetch('/api/example/'+encodeURIComponent(key));const p=await r.json();if(!r.ok)throw new Error(p.error);fill(p);await calculate();}catch(e){showError(e.message);}}
function referenceVisibility(){const fixed=customerType!=='cold_start'&&document.querySelector('input[name=reference-mode]:checked').value==='fixed';$('reference-field').classList.toggle('hidden',!fixed);$('reference-limit').required=fixed;}
function download(name,obj){const a=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify(obj,null,2)],{type:'application/json;charset=utf-8'}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function start(){
  try{const r=await fetch('/api/config');if(!r.ok)throw new Error('读取配置失败。');config=await r.json();buildFields();setCustomerType('existing',false);scenarioVisibility();updateProgress();}
  catch(e){showError('无法连接本地评分服务：'+e.message);return;}
  $('customer-form').addEventListener('submit',e=>{e.preventDefault();calculate();});
  $('customer-form').addEventListener('input',()=>{exampleNote='';markDirty();});
  document.querySelectorAll('input[name=reference-mode]').forEach(e=>e.addEventListener('change',referenceVisibility));
  document.querySelectorAll('.customer-type').forEach(button=>button.addEventListener('click',()=>setCustomerType(button.dataset.customerType)));
  $('scenario-kind').addEventListener('change',()=>{scenarioVisibility();markDirty();});
  document.querySelectorAll('.scenario-controls input').forEach(e=>e.addEventListener('input',markDirty));
  $('compare').addEventListener('click',calculate);
  $('load-example').addEventListener('click',()=>loadExample($('example').value));$('quick-demo').addEventListener('click',()=>{$('example').value='pure_limit';loadExample('pure_limit');});
  $('reset').addEventListener('click',()=>{if(busy)return;clearError();$('customer-form').reset();setCustomerType('existing',false);$('example').value='';referenceVisibility();lastResult=null;lastPayload=null;exampleNote='';dirty=false;$('results').classList.add('hidden');$('empty-state').classList.remove('hidden');$('scenario-kind').value='pure_limit';$('scenario-limit').value=50;$('scenario-debt').value=10000;$('scenario-dpd').value=30;$('scenario-payment').value=1000;scenarioVisibility();setStep('input');updateProgress();setExperienceStage('input',false);});
  $('export').addEventListener('click',()=>{if(!lastResult||dirty)return;download('信用评分结果_'+new Date().toISOString().slice(0,10)+'.json',{format:'credit-research-ui-v1',generated_at:new Date().toISOString(),input:lastPayload,result:lastResult});});
  $('print').addEventListener('click',()=>{if(lastResult&&!dirty)window.print();});
  $('import').addEventListener('change',async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>65536)throw new Error('请输入不超过 64 KB 的 JSON 文件。');let p=JSON.parse(await file.text());if(p.format==='credit-research-ui-v1')p=p.input;else if(p.current){const raw=p.previous||p.current;const inputs={};for(const f of config.fields)inputs[f.key]=raw[f.key]==null?null:f.options?raw[f.key]:raw[f.key]/f.scale;p={inputs,customer_label:'导入客户 '+(raw.SK_ID_CURR??''),reference:{mode:'fixed',limit:p.reference_limit},example_note:'导入原研究输入；请核对客户和参考额度，情景参数需按本次目的设置。'};}fill(p);clearError();}catch(err){showError('导入失败：'+err.message);}finally{e.target.value='';}});
  function openPanel(id){
    if(id==='workspace'){setExperienceStage('input');return;}
    document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('hidden',p.id!==id));
    document.querySelectorAll('.nav').forEach(b=>{b.classList.toggle('active',b.dataset.panel===id);if(b.dataset.panel===id)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
    const headings={workspace:['按步骤，完成一次评估。','每一步只呈现当前需要的信息。可随时返回修改。'],method:['每一分，都有依据。','理解模型结构、评分刻度，以及已验证的证据与限制。'],help:['让分析，清晰开始。','从输入到情景对比，了解一次完整评估的操作与边界。']};
    text('section-title',headings[id][0]);text('section-description',headings[id][1]);
    document.querySelector('.app-surface').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
  }
  document.querySelectorAll('[data-panel]').forEach(btn=>btn.addEventListener('click',()=>openPanel(btn.dataset.panel)));
  document.querySelectorAll('[data-open-panel]').forEach(btn=>btn.addEventListener('click',()=>openPanel(btn.dataset.openPanel)));
  document.querySelector('[data-start-assessment]').addEventListener('click',e=>{e.preventDefault();openPanel('workspace');});
  document.querySelectorAll('[data-step-target]').forEach(btn=>btn.addEventListener('click',()=>{const target=btn.dataset.stepTarget;if(target==='input')setExperienceStage('input',true);else if(lastResult)setExperienceStage('output',false);setStep(target,true);}));
  $('guided-demo').addEventListener('click',()=>{openPanel('workspace');$('example').value='pure_limit';loadExample('pure_limit');});
  $('cover-start').addEventListener('click',()=>setExperienceStage('input'));
  $('cover-guide').addEventListener('click',()=>setExperienceStage('input'));
  document.querySelectorAll('[data-stage-jump]').forEach(button=>button.addEventListener('click',()=>{const target=button.dataset.stageJump;if(target==='cover'){setExperienceStage('cover');window.scrollTo({top:0,behavior:'smooth'});}else if(target==='input')setExperienceStage('input');else if(lastResult)setExperienceStage('output');}));
  $('finish-export').addEventListener('click',()=>$('export').click());
  $('shutdown').addEventListener('click',async()=>{if(!confirm('退出本地评分系统？未导出的结果不会保存。'))return;try{const r=await fetch('/api/shutdown',{method:'POST',headers:{'X-Score-Token':config.token}});if(!r.ok)throw new Error('退出失败');document.body.replaceChildren();const p=document.createElement('p');p.textContent='评分系统已退出。可以关闭此页面；下次双击启动程序即可继续使用。';document.body.append(p);}catch(e){showError('服务连接已断开，请关闭运行窗口。');}});
  setExperienceStage('cover',false);
}
let flowStep='input';
function updateProgress(){
  if(!config)return;
  const required=config.fields.filter(f=>customerType==='cold_start'?['AMT_INCOME_TOTAL','limit'].includes(f.key):f.required);
  const count=required.filter(f=>{const el=$('f-'+f.key);return el.value!==''&&el.checkValidity();}).length;
  text('flow-status',flowStep==='input'?`必填进度 ${count} / ${required.length} · ${count===required.length?'可继续补充信息，或点击下方计算评分。':'请完成当前状态，再计算评分。'}`:dirty?'当前输入已改变，请更新计算后再导出结果。':'本次结果已计算 · 可返回修改信息，或继续探索变化。');
  document.querySelectorAll('.flow-nav [data-step-target]').forEach(btn=>{
    const target=btn.dataset.stepTarget;
    btn.disabled=target!=='input'&&(!lastResult||(dirty&&flowStep==='input'));
    btn.classList.toggle('completed',target==='input'?!!lastResult&&!dirty:target==='result'&&flowStep==='scenario');
  });
  $('finish-export').disabled=!lastResult||dirty;
}
function setStep(step,scroll=false){
  if(step!=='input'&&(!lastResult||(dirty&&flowStep==='input'))){text('flow-status','请先完成信息并计算评分，再进入下一步。');return;}
  flowStep=step;$('workspace').dataset.step=step;
  const content={input:['步骤 01 / 03','填写客户当前信息','完成必填信息 → 按需补充 → 设置参考额度 → 计算评分'],result:['步骤 02 / 03','读懂这一次评分','先看参考分与模型概率，再核对信息完整度和复核提示。'],scenario:['步骤 03 / 03','观察变化，理解响应','选择变化情景并更新对比。参考额度保持一致，观察行为带来的变化。']}[step];
  ['flow-number','flow-title','flow-description'].forEach((id,i)=>text(id,content[i]));
  document.querySelectorAll('.flow-nav [data-step-target]').forEach(btn=>{if(btn.dataset.stepTarget===step)btn.setAttribute('aria-current','step');else btn.removeAttribute('aria-current');});
  updateProgress();
  if(scroll){$('flow-title').focus({preventScroll:true});document.querySelector('.flow-nav').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}
}
function initExperience(){
  const reduced=matchMedia('(prefers-reduced-motion: reduce)'),canvas=$('hero-motion'),hero=$('home');
  const ctx=canvas.getContext('2d');let w=0,h=0,raf=0,visible=true,paused=reduced.matches,time=0,last=0;
  const toggle=$('motion-toggle');
  function resize(){w=hero.clientWidth;h=hero.clientHeight;const d=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(w*d);canvas.height=Math.round(h*d);ctx?.setTransform(d,0,0,d,0,0);draw();}
  function draw(){
    if(!ctx)return;ctx.clearRect(0,0,w,h);
    for(let line=0;line<5;line++){
      const y0=h*(.24+line*.1),wave=Math.sin(time*.32+line)*h*.055;
      ctx.beginPath();ctx.moveTo(-w*.12,y0);ctx.bezierCurveTo(w*.22,y0+h*.45+wave,w*.64,-h*.17+wave,w*1.12,h*(.60+line*.03));
      ctx.strokeStyle=`rgba(255, ${54+line*8}, ${74+line*5}, ${.07+line*.016})`;ctx.lineWidth=line===2?1.5:.7;ctx.stroke();
      for(let n=0;n<4;n++){
        const t=((time*.035+n*.25+line*.11)%1),u=1-t;
        const x=u*u*u*(-w*.12)+3*u*u*t*w*.22+3*u*t*t*w*.64+t*t*t*w*1.12;
        const y=u*u*u*y0+3*u*u*t*(y0+h*.45+wave)+3*u*t*t*(-h*.17+wave)+t*t*t*h*(.60+line*.03);
        ctx.beginPath();ctx.arc(x,y,line===2?2.8:1.4,0,Math.PI*2);ctx.fillStyle=line===2?'#ff7885':'#d13548';ctx.shadowBlur=12;ctx.shadowColor='#f32c48';ctx.fill();ctx.shadowBlur=0;
      }
    }
    for(let i=0;i<28;i++){const x=(i*137.7)%w,y=((i*87.3+time*(3+i%3))%(h+30))-15;ctx.fillStyle=`rgba(245,210,217,${.1+(i%4)*.05})`;ctx.fillRect(x,y,1.3,1.3);}
    canvas.dataset.frame=String(Math.round(time*100));
  }
  function tick(now){raf=0;if(paused||!visible||document.hidden)return;if(last)time+=Math.min((now-last)/1000,.05);last=now;draw();raf=requestAnimationFrame(tick);}
  function sync(){cancelAnimationFrame(raf);raf=0;last=0;hero.classList.toggle('motion-paused',paused||!visible||document.hidden);toggle.textContent=paused?'播放动效 ▷':'暂停动效 Ⅱ';toggle.setAttribute('aria-pressed',String(paused));if(!paused&&visible&&!document.hidden)raf=requestAnimationFrame(tick);else draw();}
  toggle.addEventListener('click',()=>{paused=!paused;sync();});
  reduced.addEventListener('change',()=>{paused=reduced.matches;sync();});
  document.addEventListener('visibilitychange',sync);
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync();},{threshold:.01}).observe(hero);
  new ResizeObserver(resize).observe(hero);
  hero.addEventListener('pointermove',e=>{if(paused||e.pointerType!=='mouse')return;const rect=hero.getBoundingClientRect();const x=(e.clientX-rect.left)/rect.width-.5,y=(e.clientY-rect.top)/rect.height-.5;hero.style.setProperty('--pointer-x',`${x*15}deg`);hero.style.setProperty('--pointer-y',`${-y*10}deg`);});
  hero.addEventListener('pointerleave',()=>{hero.style.setProperty('--pointer-x','0deg');hero.style.setProperty('--pointer-y','0deg');});
  const reveal=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in-view');reveal.unobserve(e.target);}}),{threshold:.12});
  document.querySelectorAll('.reveal').forEach(el=>reveal.observe(el));
  const layers=document.querySelectorAll('.guide-layer');
  layers.forEach(el=>new IntersectionObserver(entries=>entries.forEach(e=>e.target.classList.toggle('is-current',e.isIntersecting)),{rootMargin:'-20% 0px -30% 0px',threshold:.1}).observe(el));
  resize();sync();
}

start();
initExperience();
