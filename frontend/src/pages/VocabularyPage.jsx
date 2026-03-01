import { useEffect, useState } from "react";
import { api, pollTask } from "../lib/api";
import LoadingSpinner from "../components/LoadingSpinner";

export default function VocabularyPage({ onError }) {
  const [selectedText, setSelectedText] = useState("apple");
  const [sourceSentence, setSourceSentence] = useState("I eat an apple every day.");
  const [translateText, setTranslateText] = useState("book");
  const [translateContext, setTranslateContext] = useState("I read a book before sleep.");
  const [translationResult, setTranslationResult] = useState("");
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editEnglish, setEditEnglish] = useState("");
  const [editRussian, setEditRussian] = useState("");
  const [editSentence, setEditSentence] = useState("");
  const [editUrl, setEditUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [studyFlowLoading, setStudyFlowLoading] = useState(false);
  const [studyFlowStatus, setStudyFlowStatus] = useState("");
  const [translateLoading, setTranslateLoading] = useState(false);

  async function loadVocabulary() {
    setLoading(true);
    try {
      const data = await api.listVocabularyMe();
      setItems(data);
    } catch (error) {
      onError(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function addViaStudyFlow(event) {
    event.preventDefault();
    setStudyFlowLoading(true);
    setStudyFlowStatus("Отправляю задачу...");
    onError("");
    try {
      // 1. Dispatch the task — returns immediately with task_id
      const { task_id } = await api.studyFlowCaptureToVocabularyMe({
        selected_text: selectedText,
        source_sentence: sourceSentence,
      });

      // 2. Poll until done, updating status message
      setStudyFlowStatus("Обрабатываю слово...");
      await pollTask(task_id, {
        intervalMs: 800,
        maxAttempts: 90,
        onStatus: (status) => {
          if (status === "STARTED") setStudyFlowStatus("AI генерирует определение...");
          else if (status === "RETRY") setStudyFlowStatus("Повторная попытка...");
        },
      });

      setStudyFlowStatus("Готово!");
      await loadVocabulary();
    } catch (error) {
      onError(error.message);
    } finally {
      setStudyFlowLoading(false);
      setStudyFlowStatus("");
    }
  }

  async function translateInContext(event) {
    event.preventDefault();
    setTranslationResult("");
    setTranslateLoading(true);
    onError("");
    try {
      const data = await api.translateMe({ text: translateText, source_context: translateContext });
      setTranslationResult(data.translated_text);
    } catch (error) {
      onError(error.message);
    } finally {
      setTranslateLoading(false);
    }
  }

  function startEdit(item) {
    setEditingId(item.id);
    setEditEnglish(item.english_lemma);
    setEditRussian(item.russian_translation);
    setEditSentence(item.source_sentence || "");
    setEditUrl(item.source_url || "");
  }

  function cancelEdit() {
    setEditingId(null);
    setEditEnglish("");
    setEditRussian("");
    setEditSentence("");
    setEditUrl("");
  }

  async function saveEdit(event) {
    event.preventDefault();
    if (!editingId) {
      return;
    }
    try {
      await api.updateVocabularyMe(editingId, {
        english_lemma: editEnglish,
        russian_translation: editRussian,
        source_sentence: editSentence || null,
        source_url: editUrl || null,
      });
      cancelEdit();
      await loadVocabulary();
    } catch (error) {
      onError(error.message);
    }
  }

  async function deleteItem(itemId) {
    try {
      await api.deleteVocabularyMe(itemId);
      if (editingId === itemId) {
        cancelEdit();
      }
      await loadVocabulary();
    } catch (error) {
      onError(error.message);
    }
  }

  useEffect(() => {
    loadVocabulary();
  }, []);

  const filteredItems = items.filter((item) => {
    const q = search.trim().toLowerCase();
    if (!q) {
      return true;
    }
    return item.english_lemma.toLowerCase().includes(q) || item.russian_translation.toLowerCase().includes(q);
  });

  return (
    <section className="space-y-4">
      {studyFlowLoading && (
        <LoadingSpinner
          message={studyFlowStatus || "Добавляю слово в словарь..."}
          estimatedSeconds="2-5"
        />
      )}
      {translateLoading && <LoadingSpinner message="Перевожу текст..." estimatedSeconds="2-4" />}

      <header className="surface p-4 md:p-5">
        <p className="kicker">Vocabulary</p>
        <h2 className="section-title">Словарь и контекстный перевод</h2>
        <p className="muted mt-1 text-sm">Добавляйте новые слова и сразу проверяйте перевод в нужном контексте.</p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <form onSubmit={addViaStudyFlow} className="surface p-4 md:p-5 space-y-3">
          <h3 className="text-base font-extrabold text-gray-900">Добавление через Study Flow</h3>
          <input className="field" value={selectedText} onChange={(e) => setSelectedText(e.target.value)} placeholder="Выделенное слово" />
          <textarea
            className="field"
            value={sourceSentence}
            onChange={(e) => setSourceSentence(e.target.value)}
            rows={3}
            placeholder="Контекст предложения"
          />
          <div className="flex flex-wrap gap-2">
            <button className="btn-primary" type="submit" disabled={studyFlowLoading}>
              {studyFlowLoading ? "Добавляю..." : "Добавить слово"}
            </button>
          </div>
        </form>

        <form onSubmit={translateInContext} className="surface p-4 md:p-5 space-y-3">
          <h3 className="text-base font-extrabold text-gray-900">Перевод в контексте</h3>
          <input className="field" value={translateText} onChange={(e) => setTranslateText(e.target.value)} placeholder="Что перевести" />
          <textarea
            className="field"
            value={translateContext}
            onChange={(e) => setTranslateContext(e.target.value)}
            rows={3}
            placeholder="Контекст"
          />
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-primary" type="submit">Перевести</button>
            {translationResult ? <span className="chip">Результат: {translationResult}</span> : null}
          </div>
        </form>
      </div>

      <section className="surface p-4 md:p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-extrabold text-gray-900">Слова пользователя</h3>
          <input className="field max-w-xs" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Поиск EN/RU" />
        </div>

        <ul className="space-y-3">
          {filteredItems.map((item) => (
            <li key={item.id} className="surface p-4 md:p-5">
              {editingId === item.id ? (
                <form className="grid gap-2" onSubmit={saveEdit}>
                  <input className="field" value={editEnglish} onChange={(e) => setEditEnglish(e.target.value)} placeholder="English lemma" />
                  <input className="field" value={editRussian} onChange={(e) => setEditRussian(e.target.value)} placeholder="Перевод" />
                  <textarea className="field" rows={2} value={editSentence} onChange={(e) => setEditSentence(e.target.value)} placeholder="Контекст" />
                  <input className="field" value={editUrl} onChange={(e) => setEditUrl(e.target.value)} placeholder="URL источника" />
                  <div className="flex gap-2">
                    <button className="btn-primary" type="submit">Сохранить</button>
                    <button className="btn-secondary" type="button" onClick={cancelEdit}>Отмена</button>
                  </div>
                </form>
              ) : (
                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-4">
                  <div className="min-w-0">
                    <div className="text-base font-extrabold text-gray-900">{item.english_lemma} <span className="font-medium text-[var(--text)]">- {item.russian_translation}</span></div>
                    {item.context_definition_ru ? (
                      <div className="mt-2 text-sm text-gray-700">{item.context_definition_ru}</div>
                    ) : null}
                    {item.source_sentence ? <div className="muted mt-2 text-sm">{item.source_sentence}</div> : null}
                  </div>
                  <div className="flex w-32 shrink-0 flex-col gap-2 self-start">
                    <button className="btn-secondary !px-3.5 !py-2 !text-sm" type="button" onClick={() => startEdit(item)}>Редактировать</button>
                    <button className="btn-danger !px-3.5 !py-2 !text-sm" type="button" onClick={() => deleteItem(item.id)}>Удалить</button>
                  </div>
                </div>
              )}
            </li>
          ))}
          {!loading && filteredItems.length === 0 ? <li className="muted text-sm">По текущему фильтру слов нет.</li> : null}
          {loading ? <li className="muted text-sm">Загрузка...</li> : null}
        </ul>
      </section>
    </section>
  );
}
