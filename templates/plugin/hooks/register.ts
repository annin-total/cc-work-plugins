import type { Register } from 'claude-code'

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'my-plugin-hello', description: 'TODO: コマンドの説明' })
    return next(e)
  })

  on('command.run', { command: 'my-plugin-hello' }, async () => ({ text: 'Hello from my-plugin' }))
}
