export default function NavTabs({ tab, onChange }) {
  const items = [
    { id: "vocabulary", label: "Словарь" },
    { id: "review", label: "Повторение" },
    { id: "training", label: "Тренировка" },
    { id: "history", label: "История" },
  ];

  return (
    <div className="flex gap-2">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => onChange(item.id)}
          className={`rounded-md px-4 py-2 text-sm font-medium ${
            tab === item.id ? "bg-slate-900 text-white" : "bg-white text-slate-700 border border-slate-200"
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
