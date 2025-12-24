document.addEventListener('DOMContentLoaded', function(){
  const form = document.getElementById('login-form');
  const errorEl = document.getElementById('error');
  form.addEventListener('submit', async function(e){
    e.preventDefault();
    errorEl.textContent = '';
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value;
    try{
      const resp = await fetch('/login', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({username, password})
      });
      const data = await resp.json();
      if (resp.ok && data.success) {
        // redirect to main app
        window.location.href = '/';
      } else {
        errorEl.textContent = data.error || 'Invalid credentials';
      }
    } catch (err) {
      errorEl.textContent = 'Network error. Try again.';
    }
  });
});
if (resp.ok && data.success) {
    // Clear any previous chat session
    if (typeof Storage !== 'undefined') {
        localStorage.removeItem('currentChatId');
        sessionStorage.removeItem('currentChatId');
    }
    // redirect to main app
    window.location.href = '/';
}