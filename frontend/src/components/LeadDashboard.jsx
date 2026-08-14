import React, {
  useEffect,
  useState
} from 'react';

import { API_BASE } from '../config';

export default function LeadDashboard() {

  const [leads, setLeads] = useState([]);

  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState('');

  useEffect(() => {

    fetchLeads();

  }, []);

  const fetchLeads = async () => {

    try {

      const response = await fetch(
        `${API_BASE}/leads`
      );

      const data = await response.json();

      setLeads(data.results || []);

    } catch (error) {

      console.error(error);

    } finally {

      setLoading(false);
    }
  };

  const filteredLeads = leads.filter((lead) =>
    lead.name.toLowerCase().includes(
      search.toLowerCase()
    )
  );

  return (

    <div
      className="
        bg-white
        rounded-xl
        shadow-sm
        border
        p-5
      "
    >

      {/* HEADER */}
      <div
        className="
          flex
          items-center
          justify-between
          mb-5
        "
      >

        <div>

          <h2
            className="
              text-xl
              font-bold
              text-gray-900
            "
          >
            Lead Intelligence
          </h2>

          <p
            className="
              text-sm
              text-gray-500
            "
          >
            Scraped & enriched prospects
          </p>

        </div>

        <div
          className="
            text-sm
            text-gray-500
          "
        >
          Total Leads:
          {' '}
          {filteredLeads.length}
        </div>

      </div>

      {/* SEARCH */}
      <div className="mb-5">

        <input
          type="text"

          placeholder="Search companies..."

          value={search}

          onChange={(e) =>
            setSearch(e.target.value)
          }

          className="
            w-full
            border
            rounded-lg
            px-4
            py-2
            focus:outline-none
            focus:ring-2
            focus:ring-blue-500
          "
        />

      </div>

      {/* LOADING */}
      {loading && (

        <div className="text-gray-500">
          Loading leads...
        </div>
      )}

      {/* LEADS */}
      <div className="space-y-4">

        {filteredLeads.map((lead) => (

          <div
            key={lead.id}

            className="
              border
              rounded-xl
              p-4
              hover:shadow-md
              transition
            "
          >

            {/* TOP */}
            <div
              className="
                flex
                items-start
                justify-between
              "
            >

              <div>

                <h3
                  className="
                    font-semibold
                    text-lg
                    text-gray-900
                  "
                >
                  {lead.name}
                </h3>

                <p
                  className="
                    text-sm
                    text-gray-500
                  "
                >
                  {lead.industry}
                </p>

                <p
                  className="
                    text-sm
                    text-gray-500
                  "
                >
                  {lead.city},
                  {' '}
                  {lead.state}
                </p>

              </div>

              {/* ICP BADGE */}
              <div
                className="
                  bg-green-100
                  text-green-700
                  px-3
                  py-1
                  rounded-full
                  text-xs
                  font-medium
                "
              >
                ICP {lead.icp_score}
              </div>

            </div>

            {/* CONTACT INFO */}
            <div
              className="
                mt-4
                space-y-1
                text-sm
              "
            >

              {lead.email && (
                <p>
                  📧 {lead.email}
                </p>
              )}

              {lead.phone && (
                <p>
                  📞 {lead.phone}
                </p>
              )}

              {lead.website && (

                <a
                  href={lead.website}

                  target="_blank"

                  rel="noreferrer"

                  className="
                    text-blue-600
                    hover:underline
                    block
                  "
                >
                  🌐 Website
                </a>
              )}

              {lead.linkedin && (

                <a
                  href={lead.linkedin}

                  target="_blank"

                  rel="noreferrer"

                  className="
                    text-blue-600
                    hover:underline
                    block
                  "
                >
                  LinkedIn
                </a>
              )}

            </div>

            {/* ACTIONS */}
            <div
              className="
                mt-4
                flex
                flex-wrap
                gap-2
              "
            >

              {lead.phone && (

                <a
                  href={`https://wa.me/${lead.phone.replace(/\D/g, '')}`}

                  target="_blank"

                  rel="noreferrer"

                  className="
                    bg-green-600
                    text-white
                    px-3
                    py-2
                    rounded-lg
                    text-sm
                  "
                >
                  WhatsApp
                </a>
              )}

              {lead.email && (

                <a
                  href={`mailto:${lead.email}`}

                  className="
                    bg-blue-600
                    text-white
                    px-3
                    py-2
                    rounded-lg
                    text-sm
                  "
                >
                  Email
                </a>
              )}

              <button

                onClick={() =>
                  window.open(
                    `${API_BASE}/outreach/${lead.id}`,
                    '_blank'
                  )
                }

                className="
                  bg-purple-600
                  text-white
                  px-3
                  py-2
                  rounded-lg
                  text-sm
                "
              >
                Generate Outreach
              </button>

            </div>

          </div>
        ))}

      </div>

    </div>
  );
}