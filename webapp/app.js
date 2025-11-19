// webapp/app.js — pure JS UI for mini-app (works with webapp_server.py)
const apiBase = ''; // relative
let currentChatId = null;
let currentGroupTitle = '';
let selectedMembers = new Set();
let cachedMembers = [];

// helper
function $id(id){ return document.getElementById(id) }
function setInfo(text){ $id('info').innerText = text }

// load groups
async function loadGroups(){
  setInfo('Loading groups...')
  try{
    const res = await fetch('/api/groups')
    const json = await res.json()
    const list = $id('group-list')
    list.innerHTML = ''
    json.groups.forEach(g=>{
      const btn = document.createElement('button')
      btn.className = 'group-btn'
      btn.innerText = g.title
      btn.onclick = ()=> openGroup(g.chat_id, g.title)
      list.appendChild(btn)
    })
    setInfo('Tap a group to manage tag groups')
  }catch(e){
    setInfo('Error loading groups')
    console.error(e)
  }
}

async function openGroup(chatId, title){
  currentChatId = chatId
  currentGroupTitle = title || `Group ${chatId}`
  $id('group-panel').classList.remove('hidden')
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
