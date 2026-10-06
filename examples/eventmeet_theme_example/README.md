# EventMeet Theme Example

An example of an app that changes the **layout** of EventMeet's public seminar pages by replacing their
templates. Copy it, rename it, and change the templates to your own design.

- `/seminars`: a hero section and cards with a date tile (`templates/eventmeet/seminar_list.html`)
- seminar page: two columns with the registration box fixed on the right
  (`templates/eventmeet/seminar_detail.html`)

Install it next to EventMeet:

```bash
bench get-app <path-or-url-of-your-copy>
bench --site <site> install-app eventmeet_theme_example
```

See [Website design](../../docs/en/website-design.md) for the hook, the template keys and the blocks
you can override.
