// gaming-style webapp UI - loads real members and manages tag groups
const apiBase = ''; // relative
const statusEl = document.getElementById('status');
let currentChatId = null;
let cachedMembers = [];
let selected = new Set();

// small helpers
const $ = id => document.getElementById(id);
const setStatus = txt => statusEl.innerText = txt || '';

function makeRipple(card, x, y){
  let r = document.createElement('div');
  r.className = 'ripple';
  r.style.left = (x - card.getBoundingClientRect().left) + 'px';
  r.style.top = (y - card.getBoundingClientRect().top) + 'px';
  card.appendChild(r);
  setTimeout(()=> r.remove(), 600);
}

// load groups
async function loadGroups(){
  setStatus('Loading groups...');
  try{
    const res = await fetch('/api/groups');
    const json = await res.json();
    const list = $('group-list');
    list.innerHTML = '';
    json.groups.forEach(g=>{
      const b = document.createElement('button');
      b.className = 'group-btn';
      b.innerText = g.title || `Group ${g.chat_id}`;
      b.onclick = ()=> openGroup(g.chat_id, g.title);
      list.appendChild(b);
    });
    setStatus('Tap a group to manage');
  }catch(e){
    console.error(e);
    setStatus('Failed to load groups');
  }
}

async function openGroup(chatId, title){
  currentChatId = chatId;
  $('panel').classList.remove('hidden');
  $('group-title').innerText = title || `Group ${chatId}`;
  setStatus('Loading members and tag groups...');
  await renderTagGroups();
  await loadMembers();
}

// render tag groups
async function renderTagGroups(){
  try{
    const res = await fetch(`/api/taggroups/${currentChatId}`);
    const json = await res.json();
    const wrap = $('taggroups-list');
    wrap.innerHTML = '<h3>Tag groups</h3>';
    const map = json.tag_groups || {};
    if(Object.keys(map).length === 0){
      wrap.innerHTML += '<div style="opacity:.6;margin-top:8px">No tag groups</div>';
      return;
    }
    Object.keys(map).forEach(name=>{
      const row = document.createElement('div');
      row.className = 'tggroup-row';
      const left = document.createElement('div');
      left.innerText = name;
      const right = document.createElement('div');
      const trigger = document.createElement('button');
      trigger.innerText = 'Trigger';
      trigger.onclick = ()=> triggerTag(name);
      right.appendChild(trigger);
      row.appendChild(left);
      row.appendChild(right);
      wrap.appendChild(row);
    });
  }catch(e){
    console.error(e);
  }
}

// load members
async function loadMembers(){
  setStatus('Fetching members...');
  try{
    const res = await fetch(`/api/members/${currentChatId}`);
    const members = await res.json();
    cachedMembers = members;
    selected = new Set();
    renderMembers(members);
    setStatus('Select members and create tag');
  }catch(e){
    console.error(e);
    setStatus('Failed to load members');
  }
}

function renderMembers(members){
  const grid = $('members-list');
  grid.innerHTML = '';
  members.forEach((m, idx)=>{
    const card = document.createElement('div');
    card.className = 'member-card';
    card.dataset.id = m.id || '';
    card.onclick = (ev)=>{
      toggleMember(card, m.id);
      makeRipple(card, ev.clientX, ev.clientY);
    };

    const avatar = document.createElement('div');
    avatar.className = 'member-avatar';
    avatar.innerText = (m.name||'?').slice(0,1).toUpperCase();

    const name = document.createElement('div');
    name.className = 'member-name';
    name.innerText = m.name || 'Unknown';

    const check = document.createElement('div');
    check.className = 'checkmark';
    check.innerHTML = '&#10003;';

    card.appendChild(avatar);
    card.appendChild(name);
    card.appendChild(check);

    // small stagger animation delay
    card.style.animationDelay = (idx * 30) + 'ms';

    grid.appendChild(card);
  });

  // wire buttons
  $('selectAllBtn').onclick = selectAllToggle;
  $('createTgBtn').onclick = createTagGroup;
  $('backBtn').onclick = ()=> { $('panel').classList.add('hidden'); setStatus('Back to groups'); }
  $('refreshBtn').onclick = ()=> { renderTagGroups(); loadMembers(); };
}

function toggleMember(card, id){
  const is = card.classList.toggle('selected');
  if(is) selected.add(id);
  else selected.delete(id);
}

function selectAllToggle(){
  if(selected.size === cachedMembers.length){
    // unselect all
    document.querySelectorAll('.member-card.selected').forEach(c=>c.classList.remove('selected'));
    selected.clear();
  } else {
    document.querySelectorAll('.member-card').forEach(c=>{
      c.classList.add('selected');
      const id = parseInt(c.dataset.id);
      if(id) selected.add(id);
    });
  }
}

async function createTagGroup(){
  const name = $('tg-name').value.trim();
  if(!name) return alert('Enter a tag group name');
  if(selected.size === 0) return alert('Select at least one member');
  const arr = Array.from(selected);
  try{
    await fetch('/api/taggroups', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({chat_id: currentChatId, name, members: arr})
    });
    alert('Tag group created');
    $('tg-name').value = '';
    await renderTagGroups();
  }catch(e){
    console.error(e);
    alert('Failed to create');
  }
}

async function triggerTag(name){
  try{
    await fetch('/api/trigger', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({chat_id: currentChatId, tag_name: name})
    });
    alert('Triggered');
  }catch(e){
    console.error(e);
    alert('Trigger failed');
  }
}

// boot
window.addEventListener('load', ()=> loadGroups());  $id('group-panel').classList.remove('hidden')
  $id('group-title').innerText = currentGroupTitle
  setInfo('Loading tag groups and members...')
  await renderTagGroups()
  await loadMembersAndRender()
}

async function renderTagGroups(){
  const res = await fetch(`/api/taggroups/${currentChatId}`)
  const json = await res.json()
  const container = $id('taggroups-list')
  container.innerHTML = '<h3>Tag groups</h3>'
  const map = json.tag_groups || {}
  if(Object.keys(map).length === 0){
    container.innerHTML += '<div style="opacity:.6;margin-top:8px">No tag groups yet</div>'
    return
  }
  Object.keys(map).forEach(name=>{
    const row = document.createElement('div')
    row.style.display='flex'
    row.style.justifyContent='space-between'
    row.style.alignItems='center'
    row.style.marginTop='8px'
    const el = document.createElement('div')
    el.innerText = name
    const trigger = document.createElement('button')
    trigger.className='tg-btn'
    trigger.innerText='Trigger'
    trigger.onclick = ()=> triggerTag(name)
    row.appendChild(el)
    row.appendChild(trigger)
    container.appendChild(row)
  })
}

async function triggerTag(name){
  await fetch('/api/trigger', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({chat_id: currentChatId, tag_name: name})
  })
  alert('Tag triggered in group')
}

async function loadMembersAndRender(){
  try{
    const res = await fetch(`/api/members/${currentChatId}`)
    const members = await res.json()
    cachedMembers = members
    selectedMembers = new Set()
    renderMembersGrid(members)
  }catch(e){
    console.error(e)
    setInfo('Failed to load members')
  }
}

function renderMembersGrid(members){
  const container = $id('members-list')
  container.innerHTML = ''
  members.forEach(m=>{
    const card = document.createElement('div')
    card.className='member-card'
    card.dataset.id = m.id || ''
    card.onclick = ()=> toggleMember(card, m.id)
    const avatar = document.createElement('div')
    avatar.className='member-avatar'
    avatar.innerText = (m.name || '?').slice(0,1).toUpperCase()
    const name = document.createElement('div')
    name.className='member-name'
    name.innerText = m.name || 'Unknown'
    const check = document.createElement('div')
    check.className='checkmark'
    check.innerHTML = '&#10003;'
    card.appendChild(avatar)
    card.appendChild(name)
    card.appendChild(check)
    container.appendChild(card)
  })
  setInfo('Select members and click Create')
  // wire select all
  $id('selectAllBtn').onclick = selectAllToggle
  $id('createTgBtn').onclick = createTagGroup
  $id('backBtn').onclick = ()=> { $id('group-panel').classList.add('hidden'); setInfo('Back to groups'); }
}

function toggleMember(card, id){
  const selected = card.classList.toggle('selected')
  if(selected) selectedMembers.add(id)
  else selectedMembers.delete(id)
}

function selectAllToggle(){
  if(selectedMembers.size === cachedMembers.length){
    // unselect all
    document.querySelectorAll('.member-card.selected').forEach(c=>c.classList.remove('selected'))
    selectedMembers.clear()
  } else {
    document.querySelectorAll('.member-card').forEach(c=>{
      c.classList.add('selected')
      selectedMembers.add(parseInt(c.dataset.id))
    })
  }
}

async function createTagGroup(){
  const name = $id('tg-name').value.trim()
  if(!name) return alert('Enter a name')
  if(selectedMembers.size === 0) return alert('Select at least one member')
  const arr = Array.from(selectedMembers)
  await fetch('/api/taggroups', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({chat_id: currentChatId, name, members: arr})
  })
  alert('Created tag group')
  $id('tg-name').value = ''
  await renderTagGroups()
}

window.addEventListener('load', ()=>{
  loadGroups()
})
