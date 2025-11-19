document.getElementById("loadMembersBtn").onclick = async () => {
    const res = await fetch("/api/members");
    const members = await res.json();

    let output = "";
    members.forEach(m => {
        output += `<div class="member">${m}</div>`;
    });

    document.getElementById("membersList").innerHTML = output;
} 
