/**
 * SmartSearch Component
 * ======================
 * Natural language semantic search bar.
 * Real-time results as user types (debounced 500ms).
 * Shows "Found 34 matches for: pharma CMM Gujarat"
 */
import React, { useState, useCallback, useRef } from 'react';
import { semanticSearch } from '../api';

export default function SmartSearch({ onCompanyClick }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchDone, setSearchDone] = useState(false);
  const debounceRef = useRef(null);

  const performSearch = useCallback(async (searchQuery) => {
    if (!searchQuery || searchQuery.length < 3) {
      setResults([]);
      setSearchDone(false);
      return;
    }

    setLoading(true);
    try {
      const res = await semanticSearch(searchQuery);
      setResults(res.data.results || []);
      setSearchDone(true);
    } catch (err) {
      console.error('Search error:', err);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleInputChange = (e) => {
    const value = e.target.value;
    setQuery(value);

    // Debounce 500ms
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      performSearch(value);
    }, 500);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      performSearch(query);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border p-4">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder='Search leads: "pharma companies with CMM in Maharashtra"'
          className="w-full px-4 py-3 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        {loading && (
          <div className="absolute right-3 top-3">
            <div className="animate-spin h-5 w-5 border-2 border-blue-500 border-t-transparent rounded-full" />
          </div>
        )}
      </div>

      {searchDone && (
        <div className="mt-3">
          <p className="text-sm text-gray-600 mb-2">
            Found <strong>{results.length}</strong> matches for: "{query}"
          </p>

          {results.length > 0 ? (
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {results.map((company) => (
                <div
                  key={company.company_id}
                  onClick={() => onCompanyClick?.(company.company_id)}
                  className="flex items-center justify-between p-2 border rounded hover:bg-gray-50 cursor-pointer"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {company.name}
                    </p>
                    <p className="text-xs text-gray-500">
                      {company.city}, {company.state} · {company.industry}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 ml-3">
                    {company.similarity_score && (
                      <span className="text-xs text-gray-400">
                        {company.similarity_score}%
                      </span>
                    )}
                    <span className="text-xs font-medium px-2 py-0.5 bg-blue-50 text-blue-700 rounded">
                      ICP: {company.icp_score}
                    </span>
                    <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
                      {company.tier}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 text-center py-4">
              No matches found. Try different keywords.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
