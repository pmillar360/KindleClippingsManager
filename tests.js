import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseClippings } from './js/parser.js';
import { serializeClippings } from './js/serializer.js';

// ---------------------------------------------------------------------------
// Parser tests
// ---------------------------------------------------------------------------
describe('parseClippings', () => {
  it('parses a single highlight entry', () => {
    const input = [
      'The Great Gatsby (Fitzgerald, F. Scott)',
      '- Your Highlight at location 25-26 | Added on Sunday, 6 March 2022 13:23:35',
      '',
      'Some highlighted text.',
      '=========='
    ].join('\n');

    const { books, clippingOrder } = parseClippings(input);

    assert.equal(books.length, 1);
    assert.equal(books[0].title, 'The Great Gatsby');
    assert.equal(books[0].author, 'Fitzgerald, F. Scott');
    assert.equal(books[0].clippings.length, 1);

    const clip = books[0].clippings[0];
    assert.equal(clip.type, 'Highlight');
    assert.equal(clip.page, null);
    assert.equal(clip.locationStart, 25);
    assert.equal(clip.locationEnd, 26);
    assert.equal(clip.text, 'Some highlighted text.');
    assert.equal(clippingOrder.length, 1);
  });

  it('parses a bookmark (no text)', () => {
    const input = [
      'The Hobbit (J. R. R. Tolkien)',
      '- Your Bookmark on page 117 | location 1788 | Added on Monday, 4 April 2022 00:03:43',
      '',
      '',
      '=========='
    ].join('\n');

    const { books } = parseClippings(input);
    const clip = books[0].clippings[0];

    assert.equal(clip.type, 'Bookmark');
    assert.equal(clip.page, 117);
    assert.equal(clip.locationStart, 1788);
    assert.equal(clip.locationEnd, null);
    assert.equal(clip.text, '');
  });

  it('parses a highlight with page and location range', () => {
    const input = [
      'Slaughterhouse-Five (Kurt Vonnegut)',
      '- Your Highlight on page 4 | location 61-61 | Added on Monday, 11 April 2022 00:00:26',
      '',
      'it looked a lot like Dayton, Ohio',
      '=========='
    ].join('\n');

    const { books } = parseClippings(input);
    const clip = books[0].clippings[0];

    assert.equal(clip.type, 'Highlight');
    assert.equal(clip.page, 4);
    assert.equal(clip.locationStart, 61);
    assert.equal(clip.locationEnd, 61);
    assert.equal(clip.text, 'it looked a lot like Dayton, Ohio');
  });

  it('strips BOM from input', () => {
    const input = '\uFEFFSome Book (Author)\n- Your Highlight at location 1-2 | Added on Monday, 1 January 2024 00:00:00\n\ntext\n==========';
    const { books } = parseClippings(input);

    assert.equal(books.length, 1);
    assert.equal(books[0].title, 'Some Book');
  });

  it('groups clippings by book', () => {
    const input = [
      'Book A (Author A)',
      '- Your Highlight at location 10-11 | Added on Monday, 1 January 2024 00:00:00',
      '',
      'first',
      '==========',
      'Book A (Author A)',
      '- Your Highlight at location 20-21 | Added on Monday, 1 January 2024 00:00:00',
      '',
      'second',
      '==========',
      'Book B (Author B)',
      '- Your Highlight at location 5-6 | Added on Monday, 1 January 2024 00:00:00',
      '',
      'third',
      '=========='
    ].join('\n');

    const { books } = parseClippings(input);

    assert.equal(books.length, 2);
    assert.equal(books[0].clippings.length, 2);
    assert.equal(books[1].clippings.length, 1);
  });

  it('sorts clippings within a book by location', () => {
    const input = [
      'Book A (Author)',
      '- Your Highlight at location 50-51 | Added on Monday, 1 January 2024 00:00:00',
      '',
      'later',
      '==========',
      'Book A (Author)',
      '- Your Highlight at location 10-11 | Added on Monday, 1 January 2024 00:00:00',
      '',
      'earlier',
      '=========='
    ].join('\n');

    const { books } = parseClippings(input);
    const clips = books[0].clippings;

    assert.equal(clips[0].text, 'earlier');
    assert.equal(clips[1].text, 'later');
  });

  it('handles title with nested parentheses (edition info)', () => {
    const input = [
      'The Great Gatsby (AmazonClassics Edition) (Fitzgerald, F. Scott)',
      '- Your Highlight at location 25-26 | Added on Sunday, 6 March 2022 13:23:35',
      '',
      'some text',
      '=========='
    ].join('\n');

    const { books } = parseClippings(input);

    assert.equal(books[0].title, 'The Great Gatsby (AmazonClassics Edition)');
    assert.equal(books[0].author, 'Fitzgerald, F. Scott');
  });

  it('treats different title/author combos as separate books', () => {
    const input = [
      "Surely You're Joking, Mr. Feynman! (Richard P. Feynman)",
      '- Your Bookmark at location 92 | Added on Sunday, 6 March 2022 17:33:36',
      '',
      '',
      '==========',
      "Surely You're Joking Mr Feynman (Richard P Feynman)",
      '- Your Highlight at location 1357-1357 | Added on Friday, 11 March 2022 00:22:51',
      '',
      'ants left some sort of trail',
      '=========='
    ].join('\n');

    const { books } = parseClippings(input);
    assert.equal(books.length, 2);
  });

  it('preserves the raw date string', () => {
    const input = [
      'Book (Author)',
      '- Your Highlight at location 1-2 | Added on Wednesday, 30 March 2022 20:36:29',
      '',
      'text',
      '=========='
    ].join('\n');

    const { books } = parseClippings(input);
    assert.equal(books[0].clippings[0].addedOnRaw, 'Wednesday, 30 March 2022 20:36:29');
  });
});

// ---------------------------------------------------------------------------
// Serializer tests
// ---------------------------------------------------------------------------
describe('serializeClippings', () => {
  it('serializes a highlight without page', () => {
    const books = [{
      id: 'b1', title: 'Book A', author: 'Author A',
      clippings: [{
        id: 'c1', type: 'Highlight', page: null,
        locationStart: 25, locationEnd: 26,
        addedOnRaw: 'Sunday, 6 March 2022 13:23:35',
        text: 'hello world'
      }]
    }];

    const output = serializeClippings(books, ['c1']);

    assert.ok(output.includes('Book A (Author A)'));
    assert.ok(output.includes('- Your Highlight at location 25-26 | Added on Sunday, 6 March 2022 13:23:35'));
    assert.ok(output.includes('hello world'));
    assert.ok(output.includes('=========='));
  });

  it('serializes a bookmark with page', () => {
    const books = [{
      id: 'b1', title: 'The Hobbit', author: 'J. R. R. Tolkien',
      clippings: [{
        id: 'c1', type: 'Bookmark', page: 117,
        locationStart: 1788, locationEnd: null,
        addedOnRaw: 'Monday, 4 April 2022 00:03:43',
        text: ''
      }]
    }];

    const output = serializeClippings(books, ['c1']);

    assert.ok(output.includes('The Hobbit (J. R. R. Tolkien)'));
    assert.ok(output.includes('- Your Bookmark on page 117 | location 1788 | Added on Monday, 4 April 2022 00:03:43'));
  });

  it('serializes a highlight with page and location range', () => {
    const books = [{
      id: 'b1', title: 'Test', author: 'Author',
      clippings: [{
        id: 'c1', type: 'Highlight', page: 4,
        locationStart: 61, locationEnd: 61,
        addedOnRaw: 'Monday, 11 April 2022 00:00:26',
        text: 'some text'
      }]
    }];

    const output = serializeClippings(books, ['c1']);
    assert.ok(output.includes('- Your Highlight on page 4 | location 61-61 | Added on Monday, 11 April 2022 00:00:26'));
  });

  it('preserves original clipping order', () => {
    const books = [{
      id: 'b1', title: 'Book', author: 'Auth',
      clippings: [
        { id: 'c2', type: 'Highlight', page: null, locationStart: 20, locationEnd: 21, addedOnRaw: 'Mon, 1 Jan 2024 00:00:00', text: 'second' },
        { id: 'c1', type: 'Highlight', page: null, locationStart: 10, locationEnd: 11, addedOnRaw: 'Mon, 1 Jan 2024 00:00:00', text: 'first' }
      ]
    }];

    const output = serializeClippings(books, ['c1', 'c2']);
    const firstIdx = output.indexOf('first');
    const secondIdx = output.indexOf('second');

    assert.ok(firstIdx < secondIdx, 'c1 (first) should appear before c2 (second)');
  });

  it('omits deleted clippings', () => {
    const books = [{
      id: 'b1', title: 'Book', author: 'Auth',
      clippings: [
        { id: 'c1', type: 'Highlight', page: null, locationStart: 10, locationEnd: 11, addedOnRaw: 'Mon, 1 Jan 2024 00:00:00', text: 'kept' }
      ]
    }];

    // c2 is in the order but not in books (it was deleted)
    const output = serializeClippings(books, ['c1', 'c2']);

    assert.ok(output.includes('kept'));
    assert.ok(!output.includes('c2'));
  });

  it('handles book with no author', () => {
    const books = [{
      id: 'b1', title: 'Untitled', author: '',
      clippings: [{
        id: 'c1', type: 'Highlight', page: null,
        locationStart: 1, locationEnd: 2,
        addedOnRaw: 'Mon, 1 Jan 2024 00:00:00',
        text: 'text'
      }]
    }];

    const output = serializeClippings(books, ['c1']);
    assert.ok(output.startsWith('Untitled\n'));
    assert.ok(!output.includes('()'));
  });
});

// ---------------------------------------------------------------------------
// Round-trip test
// ---------------------------------------------------------------------------
describe('round-trip: parse then serialize', () => {
  it('preserves all entries from the example file', () => {
    const raw = readFileSync('My Clippings - Example.txt', 'utf8');
    const { books, clippingOrder } = parseClippings(raw);

    const totalClippings = books.reduce((n, b) => n + b.clippings.length, 0);
    assert.ok(totalClippings > 0, 'should have parsed clippings');

    const output = serializeClippings(books, clippingOrder);

    // Re-parse the serialized output
    const reparsed = parseClippings(output);
    const reparsedTotal = reparsed.books.reduce((n, b) => n + b.clippings.length, 0);

    assert.equal(reparsedTotal, totalClippings, 'round-trip should preserve all clippings');
    assert.equal(reparsed.books.length, books.length, 'round-trip should preserve all books');
  });

  it('preserves clipping text through round-trip', () => {
    const raw = readFileSync('My Clippings - Example.txt', 'utf8');
    const { books, clippingOrder } = parseClippings(raw);

    // Collect all texts
    const originalTexts = new Set();
    for (const book of books) {
      for (const clip of book.clippings) {
        if (clip.text) originalTexts.add(clip.text);
      }
    }

    const output = serializeClippings(books, clippingOrder);
    const reparsed = parseClippings(output);

    const reparsedTexts = new Set();
    for (const book of reparsed.books) {
      for (const clip of book.clippings) {
        if (clip.text) reparsedTexts.add(clip.text);
      }
    }

    for (const text of originalTexts) {
      assert.ok(reparsedTexts.has(text), `round-trip lost text: "${text.substring(0, 60)}..."`);
    }
  });
});
