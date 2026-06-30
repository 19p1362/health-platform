import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './hooks/useAuth';

import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import Login from './pages/Login';
import Landing from './pages/Landing';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import PatientSearch from './pages/PatientSearch';
import PatientChart from './pages/PatientChart';
import FhirExplorer from './pages/FhirExplorer';
import ConversionTools from './pages/ConversionTools';
import ConsentManager from './pages/ConsentManager';
import AuditLogViewer from './pages/AuditLogViewer';
import ComplianceDashboard from './pages/ComplianceDashboard';
import DocumentUpload from './pages/DocumentUpload';
import Settings from './pages/Settings';
import ExportCenter from './pages/ExportCenter';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="/patients" element={<PatientSearch />} />
              <Route path="/patients/:patientId/chart" element={<PatientChart />} />
              <Route path="/fhir" element={<FhirExplorer />} />
              <Route path="/convert" element={<ConversionTools />} />
              <Route path="/consent" element={<ConsentManager />} />
              <Route path="/audit" element={<AuditLogViewer />} />
              <Route path="/compliance" element={<ComplianceDashboard />} />
              <Route path="/upload" element={<DocumentUpload />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/exports" element={<ExportCenter />} />
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

export default App;
