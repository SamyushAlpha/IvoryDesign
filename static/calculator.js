(() => {
  const count = document.getElementById('room-count');
  const fields = document.getElementById('room-fields');
  if (!count || !fields) return;
  function renderRooms() {
    const existing = new Map(Array.from(fields.querySelectorAll('input')).map(input => [input.name, input.value]));
    fields.innerHTML = '';
    for (let index = 1; index <= Number(count.value); index += 1) {
      const row = document.createElement('fieldset');
      row.className = 'room-row';
      row.innerHTML = `<legend><span>Space ${index}</span><small>Name this room and enter dimensions</small></legend><label class="room-name-field">Room name<input type="text" name="room_${index}_name" maxlength="80" placeholder="e.g. Kitchen, Living Room, Washroom" required></label><div class="room-dimensions"><label>Length (ft)<input type="number" inputmode="decimal" name="room_${index}_length" min="0.1" max="500" step="0.01" placeholder="e.g. 12" required></label><span class="dimension-mark" aria-hidden="true">×</span><label>Width (ft)<input type="number" inputmode="decimal" name="room_${index}_width" min="0.1" max="500" step="0.01" placeholder="e.g. 10" required></label></div>`;
      row.querySelectorAll('input').forEach(input => { input.value = existing.get(input.name) || ''; });
      fields.appendChild(row);
    }
  }
  count.addEventListener('change', renderRooms);
  renderRooms();
})();
