import { NavLink, Route, Routes } from "react-router-dom";
import { AdmissionPage } from "./pages/AdmissionPage";
import { CasePage } from "./pages/CasePage";
import { ExamPage } from "./pages/ExamPage";
import { ArchivePage } from "./pages/ArchivePage";
import { DischargePage } from "./pages/DischargePage";
import { PrescriptionsPage } from "./pages/PrescriptionsPage";
import { StudiesPage } from "./pages/StudiesPage";
import { DepartmentPage } from "./pages/DepartmentPage";
import { DiaryPage } from "./pages/DiaryPage";
import { PrintPage } from "./pages/PrintPage";
import { RoundPage } from "./pages/RoundPage";
import { SettingsPage } from "./pages/SettingsPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { longToday, todayIso } from "./format";

function EyeMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    </span>
  );
}

export function App() {
  return (
    <>
      <header className="page topbar">
        <div className="brand">
          <EyeMark />
          MedQT
        </div>
        <nav className="mainnav" aria-label="Разделы">
          <NavLink to="/" end>Отделение</NavLink>
          <NavLink to="/archive">Архив</NavLink>
          <NavLink to="/stats">Статистика</NavLink>
          <NavLink to="/dictionaries">Справочники</NavLink>
        </nav>
        <span className="today">{longToday(todayIso())}</span>
      </header>
      <Routes>
        <Route path="/" element={<DepartmentPage />} />
        <Route path="/case/:caseId" element={<CasePage />} />
        <Route path="/case/:caseId/diary" element={<DiaryPage />} />
        <Route path="/case/:caseId/diary/:recordId" element={<DiaryPage />} />
        <Route path="/case/:caseId/new" element={<PlaceholderPage title="Новая запись" />} />
        <Route path="/case/:caseId/print" element={<PrintPage />} />
        <Route path="/case/:caseId/discharge" element={<DischargePage />} />
        <Route path="/case/:caseId/studies" element={<StudiesPage />} />
        <Route path="/case/:caseId/prescriptions" element={<PrescriptionsPage />} />
        <Route path="/admission" element={<AdmissionPage />} />
        <Route path="/case/:caseId/exam" element={<ExamPage />} />
        <Route path="/round" element={<RoundPage />} />
        <Route path="/archive" element={<ArchivePage />} />
        <Route path="/stats" element={<PlaceholderPage title="Статистика" />} />
        <Route path="/dictionaries" element={<SettingsPage />} />
        <Route path="*" element={<PlaceholderPage title="Страница не найдена" />} />
      </Routes>
    </>
  );
}
