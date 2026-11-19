const $ = id => document.getElementById(id);
let token = '', busy = false;
function message(text, error = false) { $('message').textContent = text; $('message').classList.toggle('error', error); }
async function api(path, options = {}) {
  const response = await fetch('/api/v1' + path, {...options, headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token, ...(options.headers || {})}});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Error HTTP ${response.status}`);
  return data;
}
const date = value => value ? new Date(value).toLocaleString('es-CO') : 'Sin lecturas';
function cell(row, text) { const td = document.createElement('td'); td.textContent = text; row.append(td); return td; }
function empty(id, columns, text) { const row = document.createElement('tr'); const td = cell(row, text); td.colSpan = columns; $(id).replaceChildren(row); }
async function refresh() {
  if (!token || busy) return;
  busy = true;
  try {
    const [summary, devices, alerts] = await Promise.all([api('/summary'), api('/devices'), api('/alerts')]);
    $('devices-count').textContent = summary.devices; $('readings-count').textContent = summary.readings;
    $('alerts-count').textContent = summary.open_alerts; $('pending-count').textContent = summary.pending;
    const selected = $('device-select').value;
    $('devices').replaceChildren(); $('device-select').replaceChildren(new Option('Selecciona un sensor', ''));
    devices.forEach(device => {
      const row = document.createElement('tr'); const name = cell(row, device.name); const site = document.createElement('small'); site.textContent = device.site; name.append(site);
      cell(row, `${device.minimum} a ${device.maximum} °C`); cell(row, device.last_temperature == null ? '—' : `${device.last_temperature} °C`);
      const status = document.createElement('span'); status.className = 'status ' + (device.state === 'NORMAL' ? 'ok' : device.state === 'SIN DATOS' ? '' : 'alert'); status.textContent = device.state; cell(row, '').append(status);
      cell(row, date(device.last_at)); const button = document.createElement('button'); button.textContent = 'Ver'; button.className = 'secondary'; button.onclick = () => history(device); cell(row, '').append(button); $('devices').append(row);
      $('device-select').add(new Option(device.name, device.id));
    });
    if (!devices.length) empty('devices', 6, 'Todavía no hay sensores. Registra el primero en el formulario.');
    $('device-select').value = selected;
    $('alerts').replaceChildren();
    alerts.forEach(alert => {
      const row = document.createElement('tr'); cell(row, alert.device_name); cell(row, alert.kind); cell(row, alert.temperature + ' °C'); cell(row, date(alert.opened_at)); cell(row, alert.resolved_at ? 'Resuelta' : 'Activa');
      if (alert.acknowledged_at) cell(row, 'Reconocida');
      else { const button = document.createElement('button'); button.textContent = 'Reconocer'; button.onclick = async () => { try { await api(`/alerts/${alert.id}/ack`, {method: 'POST'}); await refresh(); message('Alerta reconocida.'); } catch (e) { message(e.message, true); } }; cell(row, '').append(button); }
      $('alerts').append(row);
    });
    if (!alerts.length) empty('alerts', 6, 'No se han detectado temperaturas fuera de rango.');
    message('Conectado · Actualizado ' + new Date().toLocaleTimeString('es-CO'));
  } catch (error) { message(error.message, true); }
  finally { busy = false; }
}
async function history(device) {
  try { const items = await api(`/devices/${device.id}/readings`); $('history-title').textContent = 'Histórico · ' + device.name; $('history-panel').hidden = false; $('history').replaceChildren(); items.forEach(item => { const row = document.createElement('tr'); cell(row, date(item.observed_at)); cell(row, item.temperature + ' °C'); cell(row, item.event_id); $('history').append(row); }); if (!items.length) empty('history', 3, 'Este sensor todavía no tiene lecturas.'); $('history-panel').scrollIntoView({behavior: 'smooth'}); } catch (e) { message(e.message, true); }
}
$('connect').onclick = () => { token = $('token').value.trim(); if (!token) return message('Introduce un token.', true); refresh(); };
$('refresh').onclick = refresh;
$('register').onsubmit = async event => {
  event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true;
  try { const body = Object.fromEntries(new FormData(event.target)); const result = await api('/devices', {method: 'POST', body: JSON.stringify(body)}); $('credential').hidden = false; $('credential').textContent = `ID: ${result.device.id}\nCredencial: ${result.device_token}\nGuárdala: no vuelve a mostrarse desde el servidor.`; await refresh(); $('device-select').value = result.device.id; $('device-key').value = result.device_token; message('Sensor registrado. Su credencial está disponible debajo del formulario.'); }
  catch (e) { message(e.message, true); } finally { button.disabled = false; }
};
$('simulate').onsubmit = async event => {
  event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true;
  try { const data = {event_id: crypto.randomUUID(), device_id: $('device-select').value, temperature: Number($('temperature').value), observed_at: new Date().toISOString()}; await api('/telemetry', {method: 'POST', headers: {'X-Device-Key': $('device-key').value}, body: JSON.stringify(data)}); message('Lectura aceptada. Se reflejará después de procesarse.'); setTimeout(refresh, 500); }
  catch (e) { message(e.message, true); } finally { button.disabled = false; }
};
setInterval(refresh, 5000);
