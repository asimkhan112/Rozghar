import { Link } from 'react-router'
import { color, linkReset, weight } from '@/design-system'
import { LegalPage, List, P, ReviewNotice, Section } from './LegalPage'

const link = { ...linkReset, color: color.brand.base, fontWeight: weight.medium }

/**
 * Terms of service.
 *
 * The substance is the aggregator relationship: Plenilo.com indexes other
 * people's listings and sends applicants to the employer's own site. Almost
 * every clause here follows from that one fact, so it is stated first rather
 * than buried under boilerplate.
 */
export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      intro="The rules for using Plenilo.com, and the limits of what we promise."
      updated="17 August 2026"
    >
      <Section heading="What Plenilo.com is">
        <P>
          Plenilo.com is a job search engine. We index openings published by employers,
          company career pages, established job boards, universities and government
          commissions, and we link you to the employer's own application page.
        </P>
        <P>
          <strong>We are not an employer, a recruiter or a recruitment agency.</strong>{' '}
          We do not receive applications, we do not screen candidates, and we have no
          influence over who is hired. Applying happens on the employer's website, under
          the employer's terms.
        </P>
      </Section>

      <Section heading="Using the site">
        <P>You may browse, search and save listings freely, without an account. You may not:</P>
        <List
          items={[
            'Scrape, crawl or bulk-copy listings for a competing service.',
            'Interfere with the site, its infrastructure, or any measure that protects it.',
            'Submit reports or other content that is abusive, deliberately false, or designed to have a legitimate listing removed.',
            'Use the site for anything unlawful under the laws of [governing jurisdiction].',
          ]}
        />
        <P>
          We may restrict access if the site is being used in any of these ways.
        </P>
      </Section>

      <Section heading="Accuracy of listings">
        <P>
          Listings originate with third parties. We check that a listing is still open
          before publishing it and remove ones found to have closed, but{' '}
          <strong>we cannot guarantee that any listing is current, accurate, complete or
          genuine.</strong> Salary figures, deadlines and requirements are as published
          by the source.
        </P>
        <P>
          Always verify a role on the employer's own website before acting on it. If you
          find a listing that is expired, misleading or fraudulent, please report it —
          the report button is on every listing, and it is the fastest way to get it
          removed.
        </P>
      </Section>

      <Section heading="Never pay for a job">
        <P>
          A legitimate employer does not ask a candidate for money. If a listing you
          reached through Plenilo.com leads to a demand for a registration fee, a security
          deposit, training charges or payment for a visa or medical test, treat it as
          fraudulent, do not pay, and{' '}
          <Link to="/contact" style={link}>tell us</Link> so we can remove it.
        </P>
      </Section>

      <Section heading="For employers">
        <P>
          If your listing appears here and you would like it corrected or removed, contact
          us and we will act on it promptly. If you supply a listing to us for publication,
          you confirm that you are entitled to advertise the role, and that the listing is
          accurate and not discriminatory under applicable law.
        </P>
      </Section>

      <Section heading="Intellectual property">
        <P>
          The Plenilo.com name, design, and the software behind the site belong to us.
          The content of individual listings belongs to whoever published it and is shown
          here to help you find and apply for the role.
        </P>
      </Section>

      <Section heading="Availability">
        <P>
          We aim to keep the site available but do not guarantee uninterrupted service.
          It may be unavailable for maintenance, or for reasons outside our control.
        </P>
      </Section>

      <Section heading="Limitation of liability">
        <P>
          The site is provided on an "as is" basis. To the fullest extent permitted by
          law, we are not liable for loss arising from reliance on a listing, from
          anything that happens during or after an application, from an employer's
          conduct, or from the site being unavailable.
        </P>
        <P>
          Nothing here limits liability that cannot be limited by law.
        </P>
      </Section>

      <Section heading="Privacy">
        <P>
          Our <Link to="/privacy" style={link}>Privacy Policy</Link> explains what we
          record and forms part of these terms.
        </P>
      </Section>

      <Section heading="Changes and governing law">
        <P>
          We may update these terms; the date at the top of this page shows when they
          last changed, and continuing to use the site means you accept the revision.
          These terms are governed by the laws of [governing jurisdiction], and the courts of
          [city] have exclusive jurisdiction.
        </P>
      </Section>

      <Section heading="Contact">
        <P>
          Questions about these terms: <Link to="/contact" style={link}>the contact page</Link>,
          or [legal@plenilo.com].
        </P>
      </Section>

      <ReviewNotice />
    </LegalPage>
  )
}
