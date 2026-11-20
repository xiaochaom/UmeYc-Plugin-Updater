import deckyPlugin from '@decky/rollup';

const preset = deckyPlugin();

export default {
  ...preset,
  input: './.build/index.js',
  plugins: preset.plugins.filter((plugin) => plugin.name !== 'typescript'),
};
