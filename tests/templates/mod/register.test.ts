import { expect, test } from 'claude-code/testing'

test('セッション開始でコマンドを登録し、実行に答える', async ($, on) => {
  const registered: string[] = []
  on('command.register', async (_$, e) => {
    registered.push(e.name)
    return { value: { command: e.name } }
  })
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '.', surface: null, isInteractive: false })
  expect(registered).toEqual(['my-plugin-hello'])
  const { text } = await $.command.run({ command: 'my-plugin-hello' })
  expect(text).toBe('Hello from my-plugin')
})
