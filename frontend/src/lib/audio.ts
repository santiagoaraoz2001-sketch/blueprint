import { useSettingsStore } from '@/stores/settingsStore'

type SoundEffect = 'step_complete' | 'pipeline_complete' | 'error' | 'notification'

let audioCtx: AudioContext | null = null

function getAudioContext(): AudioContext {
  if (!audioCtx) {
    audioCtx = new AudioContext()
  }
  return audioCtx
}

function playTone(frequency: number, duration: number, volume: number, type: OscillatorType = 'sine', startTime = 0) {
  const ctx = getAudioContext()
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = type
  osc.frequency.value = frequency
  gain.gain.setValueAtTime(volume * 0.3, ctx.currentTime + startTime)
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + startTime + duration)
  osc.connect(gain)
  gain.connect(ctx.destination)
  osc.start(ctx.currentTime + startTime)
  osc.stop(ctx.currentTime + startTime + duration)
}

const SOUND_GENERATORS: Record<SoundEffect, (volume: number) => void> = {
  step_complete: (vol) => {
    // Short rising two-tone chime
    playTone(440, 0.12, vol, 'sine', 0)
    playTone(880, 0.15, vol, 'sine', 0.08)
  },
  pipeline_complete: (vol) => {
    // Three-note ascending fanfare
    playTone(523, 0.15, vol, 'sine', 0)
    playTone(659, 0.15, vol, 'sine', 0.12)
    playTone(784, 0.2, vol, 'sine', 0.24)
  },
  error: (vol) => {
    // Low descending buzz
    playTone(220, 0.2, vol, 'sawtooth', 0)
    playTone(110, 0.25, vol, 'sawtooth', 0.15)
  },
  notification: (vol) => {
    // Single gentle ping
    playTone(660, 0.1, vol, 'sine', 0)
  },
}

export function playSound(effect: SoundEffect) {
  const settings = useSettingsStore.getState()
  if (!settings.audioAlertsEnabled) return

  // Per-event toggles
  if (effect === 'step_complete' && !settings.audioOnStepComplete) return
  if (effect === 'pipeline_complete' && !settings.audioOnPipelineComplete) return
  if (effect === 'error' && !settings.audioOnError) return

  const volume = settings.audioVolume ?? 0.5
  try {
    SOUND_GENERATORS[effect](volume)
  } catch {
    // Audio context might fail in some environments
  }
}
