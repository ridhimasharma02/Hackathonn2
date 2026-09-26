// StockSense Vanilla JS Utilities

document.addEventListener('DOMContentLoaded', function () {
  // 1. Keyboard shortcut '/' to focus search input
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
      e.preventDefault();
      const searchInput = document.getElementById('globalSearchInput');
      if (searchInput) {
        searchInput.focus();
        searchInput.select();
      }
    }
  });

  // 2. Global search dropdown
  const searchInput = document.getElementById('globalSearchInput');
  const searchResultsDropdown = document.getElementById('globalSearchResults');

  if (searchInput && searchResultsDropdown) {
    let debounceTimer;
    searchInput.addEventListener('input', function () {
      clearTimeout(debounceTimer);
      const query = this.value.trim();

      if (query.length < 2) {
        searchResultsDropdown.classList.add('hidden');
        searchResultsDropdown.innerHTML = '';
        return;
      }

      debounceTimer = setTimeout(() => {
        fetch(`/search?q=${encodeURIComponent(query)}`)
          .then(res => res.json())
          .then(data => {
            if (!data.results || data.results.length === 0) {
              searchResultsDropdown.innerHTML = `
                <div class="px-3 py-2 text-meta-default text-outline">
                  No matching items found for "${query}"
                </div>`;
            } else {
              let html = '';
              data.results.forEach(item => {
                html += `
                  <a href="${item.url}" class="flex flex-col px-3 py-2 hover:bg-surface-container border-b border-surface-container-highest last:border-0 transition-colors">
                    <div class="flex items-center justify-between">
                      <span class="font-body-medium text-body-medium text-on-surface">${item.title}</span>
                      <span class="text-[10px] font-code-medium px-1.5 py-0.2 rounded bg-surface-container text-on-surface-variant uppercase">${item.category}</span>
                    </div>
                    <span class="text-[11px] text-on-surface-variant truncate mt-0.5">${item.subtitle}</span>
                  </a>`;
              });
              searchResultsDropdown.innerHTML = html;
            }
            searchResultsDropdown.classList.remove('hidden');
          })
          .catch(() => {
            searchResultsDropdown.classList.add('hidden');
          });
      }, 250);
    });

    document.addEventListener('click', function (e) {
      if (!searchInput.contains(e.target) && !searchResultsDropdown.contains(e.target)) {
        searchResultsDropdown.classList.add('hidden');
      }
    });
  }

  // 3. Notification Dropdown
  const notifBtn = document.getElementById('notifDropdownBtn');
  const notifDropdown = document.getElementById('notifDropdown');
  const notifBadge = document.getElementById('notifBadge');
  const notifList = document.getElementById('notifList');

  if (notifBtn && notifDropdown) {
    notifBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      notifDropdown.classList.toggle('hidden');

      if (!notifDropdown.classList.contains('hidden') && notifList) {
        fetch('/notifications')
          .then(res => res.json())
          .then(data => {
            if (notifBadge) {
              notifBadge.textContent = data.count;
              if (data.count === 0) notifBadge.classList.add('hidden');
              else notifBadge.classList.remove('hidden');
            }
            if (data.notifications.length === 0) {
              notifList.innerHTML = `<div class="p-4 text-center text-meta-default text-outline">No pending notifications. All tasks up to date!</div>`;
            } else {
              let html = '';
              data.notifications.forEach(n => {
                const dotColor = n.type === 'error' ? 'bg-error' : (n.type === 'warning' ? 'bg-amber-500' : 'bg-primary-container');
                html += `
                  <a href="${n.url}" class="flex items-start gap-2.5 p-3 hover:bg-surface-container border-b border-surface-container-highest last:border-0 transition-colors">
                    <span class="w-2 h-2 rounded-full ${dotColor} mt-1.5 shrink-0"></span>
                    <div class="flex flex-col min-w-0">
                      <span class="font-body-medium text-body-medium text-on-surface truncate">${n.title}</span>
                      <span class="text-[11px] text-on-surface-variant truncate">${n.desc}</span>
                    </div>
                  </a>`;
              });
              notifList.innerHTML = html;
            }
          });
      }
    });

    document.addEventListener('click', function (e) {
      if (!notifDropdown.contains(e.target) && !notifBtn.contains(e.target)) {
        notifDropdown.classList.add('hidden');
      }
    });
  }

  // 4. User Profile Dropdown
  const profileBtn = document.getElementById('userProfileMenuBtn');
  const profileMenu = document.getElementById('userProfileMenu');
  if (profileBtn && profileMenu) {
    profileBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      profileMenu.classList.toggle('hidden');
    });
    document.addEventListener('click', function (e) {
      if (!profileMenu.contains(e.target) && !profileBtn.contains(e.target)) {
        profileMenu.classList.add('hidden');
      }
    });
  }

  // 5. Modals Helper
  window.openModal = function (modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.remove('hidden');
  };

  window.closeModal = function (modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.add('hidden');
  };
});
