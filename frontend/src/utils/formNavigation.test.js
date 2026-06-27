import {
  getFocusableFields,
  handleFormNavKeyDown,
  isFocusableField,
  sortByVisualPosition,
} from './formNavigation';

function mount(html) {
  const root = document.createElement('div');
  root.innerHTML = html;
  document.body.appendChild(root);
  return root;
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('formNavigation', () => {
  test('getFocusableFields skips disabled and data-nav-skip', () => {
    const root = mount(`
      <input id="a" />
      <input id="b" disabled />
      <input id="c" data-nav-skip />
      <button role="combobox" id="d"></button>
    `);
    const fields = getFocusableFields(root);
    expect(fields.map((el) => el.id)).toEqual(['a', 'd']);
  });

  test('Enter moves to next field', () => {
    const root = mount(`
      <input id="a" />
      <input id="b" />
    `);
    const a = root.querySelector('#a');
    const b = root.querySelector('#b');
    a.focus();
    const prevented = { value: false };
    handleFormNavKeyDown(
      {
        key: 'Enter',
        target: a,
        shiftKey: false,
        preventDefault() {
          prevented.value = true;
        },
      },
      root,
    );
    expect(prevented.value).toBe(true);
    expect(document.activeElement).toBe(b);
  });

  test('ArrowDown on number input does not navigate', () => {
    const root = mount(`
      <input id="a" type="number" />
      <input id="b" />
    `);
    const a = root.querySelector('#a');
    a.focus();
    handleFormNavKeyDown(
      { key: 'ArrowDown', target: a, altKey: false, preventDefault: jest.fn() },
      root,
    );
    expect(document.activeElement).toBe(a);
  });

  test('sortByVisualPosition orders top-to-bottom then left-to-right', () => {
    const a = { getBoundingClientRect: () => ({ top: 0, left: 0 }) };
    const b = { getBoundingClientRect: () => ({ top: 0, left: 100 }) };
    const c = { getBoundingClientRect: () => ({ top: 50, left: 0 }) };
    expect(sortByVisualPosition([c, b, a])).toEqual([a, b, c]);
  });

  test('textarea Enter without ctrl does not navigate', () => {
    const root = mount(`
      <textarea id="a"></textarea>
      <input id="b" />
    `);
    const a = root.querySelector('#a');
    a.focus();
    handleFormNavKeyDown(
      { key: 'Enter', target: a, shiftKey: false, ctrlKey: false, metaKey: false, preventDefault: jest.fn() },
      root,
    );
    expect(document.activeElement).toBe(a);
  });
});
