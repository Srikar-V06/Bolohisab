const listen = document.querySelector('#listen')
const synthesis = window.speechSynthesis
let reading

if (listen) {
  synthesis?.getVoices()
  listen.addEventListener('click', () => {
    const message = document.querySelector('#playback-status')
    message.textContent = ''
    if (reading) {
      reading = undefined
      synthesis.cancel()
      listen.textContent = listen.dataset.start
      return
    }
    const locale = document.documentElement.lang.toLowerCase()
    const voices = synthesis?.getVoices() ?? []
    const voice = voices.find((option) => option.lang.toLowerCase() === locale)
      ?? voices.find((option) => option.lang.toLowerCase().split('-')[0] === locale.split('-')[0])
    if (!voice || typeof SpeechSynthesisUtterance !== 'function') {
      message.textContent = listen.dataset.unavailable
      return
    }
    const text = Array.from(document.querySelectorAll('#receipt h1, #receipt p, #receipt dt, #receipt dd'))
      .map((element) => element.textContent).join('. ')
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.voice = voice
    utterance.lang = voice.lang
    reading = utterance
    listen.textContent = listen.dataset.stop
    function finish(failed) {
      if (reading !== utterance) return
      reading = undefined
      listen.textContent = listen.dataset.start
      if (failed) message.textContent = listen.dataset.unavailable
    }
    utterance.onend = () => finish(false)
    utterance.onerror = () => finish(true)
    try {
      synthesis.speak(utterance)
    } catch {
      finish(true)
    }
  })
}

function claimInPaise(input) {
  const decimal = input.trim().replace(/[०-९]/g, (digit) => String(digit.charCodeAt(0) - 0x0966))
    .replace(/^−/, '-')
  const amount = /^(-?)([0-9]{1,17})(?:[.,]([0-9]{1,2}))?$/.exec(decimal)
  if (!amount) return undefined
  const [, sign, whole, fraction = ''] = amount
  const digits = (whole + fraction.padEnd(2, '0')).replace(/^0+(?=\d)/, '')
  return digits === '0' ? digits : sign + digits
}

const actions = document.querySelector('#response-actions')
if (actions) {
  const status = document.querySelector('#action-status')
  const form = document.querySelector('#dispute')
  const buttons = Array.from(actions.querySelectorAll('button'))
  let busy = false

  async function send(action, body) {
    if (busy) return
    busy = true
    status.textContent = ''
    buttons.forEach((button) => { button.disabled = true })
    try {
      const response = await fetch(window.location.pathname + '/' + action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (response.ok) {
        window.location.reload()
        return
      }
      status.textContent = response.status === 409 ? actions.dataset.conflict
        : response.status === 422 ? actions.dataset.invalid : actions.dataset.failed
    } catch {
      status.textContent = actions.dataset.failed
    }
    busy = false
    buttons.forEach((button) => { button.disabled = false })
  }

  document.querySelector('#confirm').addEventListener('click', () => send('confirm', {}))
  form.addEventListener('submit', (event) => {
    event.preventDefault()
    const amount = claimInPaise(document.querySelector('#claim').value)
    const reason = document.querySelector('#reason').value.trim()
    if (!amount || !reason) {
      status.textContent = !amount ? actions.dataset.invalid : actions.dataset.failed
      return
    }
    send('dispute', { claimed_amount_paise: amount, reason })
  })
}
