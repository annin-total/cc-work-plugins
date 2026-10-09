import type { Register } from 'claude-code'

const COMMAND = 'my-plugin-hello'

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: COMMAND, description: 'TODO: コマンドの説明' })
    return next(e)
  })

  on('command.run', { command: COMMAND }, async () => ({ text: 'Hello from my-plugin' }))
}
