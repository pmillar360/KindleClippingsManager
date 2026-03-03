import { parseClippings } from './parser.js';
import { serializeClippings } from './serializer.js';

const { createApp, ref, computed, watch, nextTick } = Vue;

const app = createApp({
  setup() {
    // --- State ---
    const books = ref([]);
    const clippingOrder = ref([]);
    const isDirty = ref(false);
    const fileName = ref('');
    const selectedBookId = ref(null);
    const sortBy = ref('title'); // 'title' or 'author'
    const searchQuery = ref('');
    const searchMode = ref('books'); // 'books' or 'content'
    const editingClipId = ref(null);
    const editText = ref('');
    const contentSearchResults = ref([]); // for full-text search results
    const clippingSearchQuery = ref('');

    // --- Computed ---

    // Sorted & filtered book list
    const filteredBooks = computed(() => {
      let list = [...books.value];

      // Filter by search query (books mode)
      if (searchQuery.value && searchMode.value === 'books') {
        const q = searchQuery.value.toLowerCase();
        list = list.filter(b =>
          b.title.toLowerCase().includes(q) ||
          b.author.toLowerCase().includes(q)
        );
      }

      // Sort
      if (sortBy.value === 'title') {
        list.sort((a, b) => a.title.localeCompare(b.title));
      } else {
        list.sort((a, b) => a.author.localeCompare(b.author));
      }

      return list;
    });

    // Selected book object
    const selectedBook = computed(() => {
      if (!selectedBookId.value) return null;
      return books.value.find(b => b.id === selectedBookId.value) || null;
    });

    // Clippings for the selected book, sorted by location, filtered by clipping search
    const selectedClippings = computed(() => {
      if (!selectedBook.value) return [];
      let clips = [...selectedBook.value.clippings].sort(
        (a, b) => a.locationStart - b.locationStart
      );
      if (clippingSearchQuery.value) {
        const q = clippingSearchQuery.value.toLowerCase();
        clips = clips.filter(c => c.text && c.text.toLowerCase().includes(q));
      }
      return clips;
    });

    // Duplicate detection: clippings with same locationStart+locationEnd+text in same book
    const duplicateIds = computed(() => {
      const dupes = new Set();
      for (const book of books.value) {
        const seen = new Map();
        for (const clip of book.clippings) {
          const key = `${clip.locationStart}:${clip.locationEnd}:${clip.text}`;
          if (seen.has(key)) {
            dupes.add(clip.id);
            dupes.add(seen.get(key));
          } else {
            seen.set(key, clip.id);
          }
        }
      }
      return dupes;
    });

    // Count duplicates for selected book
    const selectedBookDuplicateCount = computed(() => {
      if (!selectedBook.value) return 0;
      return selectedBook.value.clippings.filter(c => duplicateIds.value.has(c.id)).length;
    });

    // Full-text content search results
    const contentResults = computed(() => {
      if (!searchQuery.value || searchMode.value !== 'content') return [];
      const q = searchQuery.value.toLowerCase();
      const results = [];
      for (const book of books.value) {
        for (const clip of book.clippings) {
          if (clip.text && clip.text.toLowerCase().includes(q)) {
            results.push({ book, clipping: clip });
          }
        }
      }
      return results;
    });

    // --- Methods ---

    async function openFile() {
      if (isDirty.value) {
        const ok = confirm('You have unsaved changes. Loading a new file will discard them. Continue?');
        if (!ok) return;
      }

      const input = document.createElement('input');
      input.type = 'file';
      input.accept = '.txt';
      input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        fileName.value = file.name;
        const text = await file.text();
        loadText(text);
      };
      input.click();
    }

    function loadText(text) {
      const result = parseClippings(text);
      books.value = result.books;
      clippingOrder.value = result.clippingOrder;
      isDirty.value = false;
      selectedBookId.value = null;
      editingClipId.value = null;
      searchQuery.value = '';
    }

    function downloadFile() {
      const content = serializeClippings(books.value, clippingOrder.value);
      const blob = new Blob([content], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName.value || 'My Clippings.txt';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      isDirty.value = false;
    }

    function selectBook(bookId) {
      editingClipId.value = null;
      clippingSearchQuery.value = '';
      selectedBookId.value = bookId;
    }

    function startEdit(clip) {
      editingClipId.value = clip.id;
      editText.value = clip.text;
    }

    function cancelEdit() {
      editingClipId.value = null;
      editText.value = '';
    }

    function saveEdit(clip) {
      clip.text = editText.value;
      editingClipId.value = null;
      editText.value = '';
      isDirty.value = true;
    }

    function deleteClipping(clip) {
      const ok = confirm('Delete this clipping? This cannot be undone.');
      if (!ok) return;

      const book = selectedBook.value;
      if (!book) return;

      book.clippings = book.clippings.filter(c => c.id !== clip.id);
      // Remove from order
      clippingOrder.value = clippingOrder.value.filter(id => id !== clip.id);
      isDirty.value = true;

      // If book has no more clippings, remove it
      if (book.clippings.length === 0) {
        books.value = books.value.filter(b => b.id !== book.id);
        selectedBookId.value = null;
      }
    }

    function deleteBook(book) {
      if (!book) return;
      const count = book.clippings.length;
      const ok = confirm(`Delete "${book.title}" and all ${count} clipping(s)? This cannot be undone.`);
      if (!ok) return;

      // Remove all clippings from order
      const clipIds = new Set(book.clippings.map(c => c.id));
      clippingOrder.value = clippingOrder.value.filter(id => !clipIds.has(id));

      books.value = books.value.filter(b => b.id !== book.id);
      if (selectedBookId.value === book.id) {
        selectedBookId.value = null;
      }
      isDirty.value = true;
    }

    function removeDuplicates() {
      if (!selectedBook.value) return;
      const book = selectedBook.value;
      const seen = new Map();
      const toRemove = [];

      for (const clip of book.clippings) {
        const key = `${clip.locationStart}:${clip.locationEnd}:${clip.text}`;
        if (seen.has(key)) {
          toRemove.push(clip.id);
        } else {
          seen.set(key, clip.id);
        }
      }

      if (toRemove.length === 0) return;

      const ok = confirm(`Remove ${toRemove.length} duplicate clipping(s)?`);
      if (!ok) return;

      const removeSet = new Set(toRemove);
      book.clippings = book.clippings.filter(c => !removeSet.has(c.id));
      clippingOrder.value = clippingOrder.value.filter(id => !removeSet.has(id));
      isDirty.value = true;
    }

    function navigateToClipping(bookId, clipId) {
      selectedBookId.value = bookId;
      // Wait for DOM update, then scroll to the clipping
      nextTick(() => {
        const el = document.getElementById(clipId);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    }

    function formatDate(clip) {
      if (clip.addedOn) {
        return clip.addedOn.toLocaleDateString('en-GB', {
          month: 'short',
          year: 'numeric'
        });
      }
      return clip.addedOnRaw || '';
    }

    function formatDateFull(clip) {
      if (clip.addedOn) {
        return clip.addedOn.toLocaleDateString('en-GB', {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        });
      }
      return clip.addedOnRaw || '';
    }

    function locationStr(clip) {
      let s = `loc ${clip.locationStart}`;
      if (clip.locationEnd && clip.locationEnd !== clip.locationStart) {
        s += `-${clip.locationEnd}`;
      }
      return s;
    }

    function highlightMatch(text, query) {
      if (!query) return escapeHtml(text);
      const escaped = escapeHtml(text);
      const q = escapeHtml(query);
      const regex = new RegExp(`(${escapeRegex(q)})`, 'gi');
      return escaped.replace(regex, '<mark>$1</mark>');
    }

    function escapeHtml(str) {
      const d = document.createElement('div');
      d.textContent = str;
      return d.innerHTML;
    }

    function escapeRegex(str) {
      return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    // Warn before unload if dirty
    window.addEventListener('beforeunload', (e) => {
      if (isDirty.value) {
        e.preventDefault();
        e.returnValue = '';
      }
    });

    return {
      books, isDirty, fileName, selectedBookId, sortBy, searchQuery,
      searchMode, editingClipId, editText, clippingSearchQuery,
      filteredBooks, selectedBook, selectedClippings,
      duplicateIds, selectedBookDuplicateCount, contentResults,
      openFile, downloadFile, selectBook,
      startEdit, cancelEdit, saveEdit,
      deleteClipping, deleteBook, removeDuplicates,
      navigateToClipping,
      formatDate, formatDateFull, locationStr, highlightMatch
    };
  }
});

app.mount('#app');
