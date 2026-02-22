export default function LoadingSpinner({ message = "Загрузка...", estimatedSeconds = null }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 p-4">
      <div className="surface w-full max-w-sm p-6">
        <div className="flex flex-col items-center">
          <div className="h-14 w-14 animate-spin rounded-full border-4 border-blue-100 border-t-blue-600" />
          <p className="mt-4 text-center text-base font-semibold text-gray-900">{message}</p>
          {estimatedSeconds ? (
            <p className="muted mt-2 text-center text-sm">Обычно занимает {estimatedSeconds} секунд</p>
          ) : null}
          <p className="muted mt-2 text-center text-xs">Подготавливаем персонализированное задание...</p>
        </div>
      </div>
    </div>
  );
}
