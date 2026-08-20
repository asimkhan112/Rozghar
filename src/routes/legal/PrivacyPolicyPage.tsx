import { Link } from 'react-router'
import { color, linkReset, weight } from '@/design-system'
import { LegalPage, List, P, ReviewNotice, Section } from './LegalPage'

const link = { ...linkReset, color: color.brand.base, fontWeight: weight.medium }

/**
 * Privacy policy.
 *
 * Written against what the product actually does rather than from a template:
 * every collection claim below corresponds to a real table or a real browser
 * key. That matters more than length — a policy describing collection that
 * does not happen is as wrong as one omitting collection that does.
 */
export default function PrivacyPolicyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      intro="What Plenilo.com records when you use the site, and what it does not."
      updated="17 August 2026"
    >
      <Section heading="The short version">
        <P>
          You do not need an account to use Plenilo.com, and we do not ask for one. We
          do not collect your name, phone number or CV. Jobs you save stay in your own
          browser. We record anonymous usage measurements so we can tell which listings
          are useful and which searches return nothing.
        </P>
      </Section>

      <Section heading="Who we are">
        <P>
          Plenilo.com is operated by [legal entity name], [registered address], [country of registration].
          For any question about this policy or your data, write to{' '}
          <Link to="/contact" style={link}>our contact page</Link> or email
          [privacy@plenilo.com].
        </P>
      </Section>

      <Section heading="What we collect">
        <P>
          <strong>Nothing that identifies you personally as a job seeker.</strong> There
          is no registration, no profile and no CV upload. Specifically, we record:
        </P>
        <List
          items={[
            <>
              <strong>An anonymous session identifier.</strong> A random value generated
              in your browser and stored there. It identifies a browser, not a person,
              and lets us see that one visit searched, then opened a listing, then
              clicked apply. Clearing your browser storage replaces it.
            </>,
            <>
              <strong>Usage events.</strong> Which listings were viewed, saved, shared or
              applied to; which searches were run and how many results they returned;
              which filters were used. Each event carries the session identifier, a
              broad device type (mobile, tablet or desktop), a country code and the
              website that referred you — never a full browsing history.
            </>,
            <>
              <strong>Search terms.</strong> Exactly what you typed into the search box.
              Please do not type personal information into it.
            </>,
            <>
              <strong>A one-way hash of your IP address</strong>, and only when you submit
              a report about a listing. It is used to stop one person flooding the queue
              and cannot be converted back into your address.
            </>,
          ]}
        />
        <P>
          We do <strong>not</strong> collect your name, email address, phone number,
          CNIC, date of birth, salary history or CV. We do not sell data to anyone, and
          we do not run third-party advertising or tracking scripts.
        </P>
      </Section>

      <Section heading="What is stored in your browser">
        <List
          items={[
            <>
              <strong>Saved jobs.</strong> Kept in your browser's local storage, on your
              device. They are never uploaded, which is also why they do not follow you
              to another phone or computer.
            </>,
            <>
              <strong>Display preferences</strong>, such as your last-used filters.
            </>,
            <>
              <strong>The anonymous session identifier</strong> described above.
            </>,
            <>
              <strong>An administrator sign-in cookie</strong>, set only for staff who
              sign in to the admin console. It is HTTP-only, restricted to this site,
              and is never set for ordinary visitors.
            </>,
          ]}
        />
        <P>
          Clearing your browser data removes all of these, including your saved jobs.
        </P>
      </Section>

      <Section heading="Why we collect it">
        <List
          items={[
            'To show which categories and locations actually have openings.',
            'To find searches that return nothing, so we know what the catalogue is missing.',
            'To detect listings that have expired or are being reported as broken.',
            'To measure whether a job source is worth continuing to index.',
          ]}
        />
      </Section>

      <Section heading="How long we keep it">
        <List
          items={[
            <>Usage events: <strong>400 days</strong>, then deleted automatically.</>,
            <>Search logs: <strong>180 days</strong>, then deleted automatically.</>,
            <>Aggregated daily totals, which contain no session identifiers: <strong>800 days</strong>.</>,
            <>Reports about listings: kept while the listing is live and for a reasonable period after it closes.</>,
          ]}
        />
        <P>Deletion runs on a schedule rather than by hand, so it is not forgotten.</P>
      </Section>

      <Section heading="Who else sees it">
        <P>
          Our hosting and database providers process data on our behalf under contract.
          Beyond that, nobody. We do not share, sell or rent usage data.
        </P>
        <P>
          When you click <strong>Apply</strong>, you leave Plenilo.com for the employer's
          own website. What happens there is governed by that employer's privacy policy,
          not this one. We have no visibility into whether you applied or what you sent.
        </P>
      </Section>

      <Section heading="Your choices">
        <List
          items={[
            'Clear your browser data to remove your saved jobs, preferences and session identifier.',
            'Use a private browsing window, which discards all of it when you close the window.',
            <>
              Ask us what is held against a session identifier, or ask us to delete it, via{' '}
              <Link to="/contact" style={link}>the contact page</Link>. Because the data is
              anonymous, we may need you to supply the identifier from your own browser
              before we can find it.
            </>,
          ]}
        />
      </Section>

      <Section heading="Children">
        <P>
          Plenilo.com is aimed at people seeking employment and is not directed at children
          under 13. We do not knowingly collect information from them.
        </P>
      </Section>

      <Section heading="Changes">
        <P>
          If this policy changes materially we will update the date at the top of this
          page. Continuing to use the site after a change means you accept the revised
          policy.
        </P>
      </Section>

      <ReviewNotice />
    </LegalPage>
  )
}
